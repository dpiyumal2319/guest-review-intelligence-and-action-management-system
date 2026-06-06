from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import sentiment as sentiment_module
from app.ml import issue_classifier as issue_classifier_module
from app.connectors.registry import CONNECTORS
from app.database import get_session
from app.ingestion import normalized_content_hash, run_mock_connector_by_key, run_payload_ingestion, run_seed_ingestion
from app.analysis import score_reputation_risk
from app.main import app
from app.models import (
    ActionTicket,
    CategoryDepartmentMapping,
    DemoRole,
    Department,
    IngestionRun,
    IssueCategory,
    NormalizedReview,
    RawReview,
    ReviewAnalysis,
    ReviewIssueCategoryPrediction,
    ReviewSource,
    ReputationRiskThreshold,
    TicketEvent,
)
from app.seed import seed_reference_config
from app import semantic_similarity as semantic_similarity_module
from app.semantic_similarity import analyze_semantic_similarity, get_semantic_similarity_analyzer
from app.sentiment import get_sentiment_analyzer
from app.ml.issue_classifier import get_issue_category_classifier


@pytest.fixture(autouse=True)
def fake_model_runtimes(monkeypatch):
    class FakeSentimentPipeline:
        def __init__(self) -> None:
            self.model = type(
                "FakeModel",
                (),
                {"config": type("FakeConfig", (), {"_commit_hash": "sentiment-test-revision"})()},
            )()

        def __call__(self, text: str, truncation: bool = True) -> list[dict[str, float | str]]:
            assert truncation is True
            normalized = text.lower()
            if any(term in normalized for term in ("dirty", "slow", "broken", "not clean", "cleaned", "bathroom", "difficult", "noise", "audible")):
                return [{"label": "2 stars", "score": 0.88}]
            if "helpful" in normalized or "excellent" in normalized:
                return [{"label": "5 stars", "score": 0.93}]
            return [{"label": "3 stars", "score": 0.67}]

    class FakeZeroShotPipeline:
        def __init__(self) -> None:
            self.model = type(
                "FakeModel",
                (),
                {"config": type("FakeConfig", (), {"_commit_hash": "issue-test-revision"})()},
            )()

        def __call__(self, text: str, candidate_labels: list[str], multi_label: bool = False, truncation: bool = True) -> dict:
            assert multi_label is False
            assert truncation is True
            normalized = text.lower()
            ranking = [
                ("Cleanliness", 0.93 if any(term in normalized for term in ("dirty", "clean", "cleaned", "bathroom", "sink")) else 0.05),
                ("Booking and Check-in", 0.91 if "check-in" in normalized or "booking" in normalized or "queue" in normalized else 0.05),
                ("Service Delay", 0.89 if "slow" in normalized or "delay" in normalized or "queue" in normalized else 0.05),
                ("Staff Behavior", 0.88 if "staff" in normalized or "rude" in normalized or "helpful" in normalized else 0.05),
                ("Room Condition", 0.87 if "broken" in normalized or "shower" in normalized or "maintenance" in normalized else 0.05),
                ("Food and Beverage", 0.86 if "food" in normalized or "breakfast" in normalized or "restaurant" in normalized else 0.05),
                ("Noise and Events", 0.84 if "noise" in normalized or "music" in normalized or "event" in normalized else 0.05),
                ("Pricing and Value", 0.83 if "price" in normalized or "value" in normalized or "billing" in normalized else 0.05),
                ("Amenities and Facilities", 0.82 if "pool" in normalized or "wifi" in normalized or "wi-fi" in normalized else 0.05),
                ("Positive General", 0.90 if "excellent" in normalized or "great" in normalized or "helpful" in normalized else 0.05),
                ("Other or Uncategorized", 0.10),
            ]
            ranked = sorted(ranking, key=lambda item: item[1], reverse=True)
            labels = [label for label, _ in ranked if label in candidate_labels]
            scores = [score for label, score in ranked if label in candidate_labels]
            return {"labels": labels, "scores": scores}

    monkeypatch.setattr(sentiment_module, "_load_transformer_pipeline", lambda **_: FakeSentimentPipeline())
    monkeypatch.setattr(issue_classifier_module, "_load_transformer_pipeline", lambda **_: FakeZeroShotPipeline())
    get_sentiment_analyzer.cache_clear()
    get_issue_category_classifier.cache_clear()
    yield
    get_sentiment_analyzer.cache_clear()
    get_issue_category_classifier.cache_clear()


def test_reputation_risk_scoring_covers_label_thresholds() -> None:
    analyzed_at = datetime(2026, 5, 22, tzinfo=UTC)

    low_score, low_label, low_factors = score_reputation_risk(
        rating=5.0,
        sentiment_score=0.80,
        issue_category_code="positive_general",
        review_date=analyzed_at,
        analyzed_at=analyzed_at,
        urgency_score=0,
        recurrence_count=1,
        duplicate_signal=False,
        normalized_payload={},
    )
    medium_score, medium_label, medium_factors = score_reputation_risk(
        rating=4.0,
        sentiment_score=0.10,
        issue_category_code="cleanliness",
        review_date=analyzed_at - timedelta(days=2),
        analyzed_at=analyzed_at,
        urgency_score=0,
        recurrence_count=1,
        duplicate_signal=False,
        normalized_payload={},
    )
    high_score, high_label, high_factors = score_reputation_risk(
        rating=2.0,
        sentiment_score=-0.50,
        issue_category_code="booking_checkin",
        review_date=analyzed_at - timedelta(days=1),
        analyzed_at=analyzed_at,
        urgency_score=0,
        recurrence_count=1,
        duplicate_signal=False,
        normalized_payload={},
    )
    critical_score, critical_label, critical_factors = score_reputation_risk(
        rating=1.0,
        sentiment_score=-0.90,
        issue_category_code="cleanliness",
        review_date=analyzed_at,
        analyzed_at=analyzed_at,
        urgency_score=15,
        recurrence_count=3,
        duplicate_signal=True,
        normalized_payload={"provider_helpful_votes": 4, "provider_url": "https://example.test/review"},
    )

    assert (low_label, medium_label, high_label, critical_label) == ("low", "medium", "high", "critical")
    assert low_score < medium_score < high_score < critical_score
    assert medium_factors["weights"]["recency"] > 0
    assert "low rating" in high_factors["operational_explanations"]
    assert "visible platform engagement" in critical_factors["operational_explanations"]
    assert low_factors["thresholds"] == {"low": "0-29", "medium": "30-49", "high": "50-74", "critical": "75-100"}


def migrate(database_url: str) -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


def _ingest_single_review(session: Session, *, external_review_id: str) -> NormalizedReview:
    run = run_payload_ingestion(
        session,
        source_code="google_business_profile",
        connector_key="test_sentiment_runtime",
        payloads=[
            {
                "source_code": "google_business_profile",
                "external_review_id": external_review_id,
                "reviewer_name": "Guest Runtime",
                "review_date": "2026-05-20T10:00:00+00:00",
                "rating": 4.0,
                "language": "en",
                "title": "Helpful team",
                "body": "Helpful staff but the queue was slow.",
                "sentiment_label": "mixed",
                "sentiment_score": 0.0,
                "issue_category_code": "service_delay",
                "reputation_risk": "medium",
                "department_code": "front_office",
            }
        ],
    )
    assert run.status == "completed", run.errors
    review = session.scalar(
        select(NormalizedReview).where(NormalizedReview.external_review_id == external_review_id)
    )
    assert review is not None
    assert review.analysis is not None
    return review


def _ingest_semantic_reviews(session: Session, *, connector_key: str) -> list[NormalizedReview]:
    run_payload_ingestion(
        session,
        source_code="google_business_profile",
        connector_key=connector_key,
        payloads=[
            {
                "source_code": "google_business_profile",
                "external_review_id": f"{connector_key}-001",
                "reviewer_name": "Guest One",
                "review_date": "2026-05-20T10:00:00+00:00",
                "rating": 2.0,
                "language": "en",
                "title": "Slow check-in queue",
                "body": "The front desk check-in queue was very slow and took too long.",
                "sentiment_label": "negative",
                "sentiment_score": -0.65,
                "issue_category_code": "booking_checkin",
                "reputation_risk": "high",
                "department_code": "front_office",
            },
            {
                "source_code": "google_business_profile",
                "external_review_id": f"{connector_key}-002",
                "reviewer_name": "Guest Two",
                "review_date": "2026-05-21T12:00:00+00:00",
                "rating": 2.0,
                "language": "en",
                "title": "Front desk delay",
                "body": "Check-in at the front desk took a very long time because the queue was slow.",
                "sentiment_label": "negative",
                "sentiment_score": -0.62,
                "issue_category_code": "booking_checkin",
                "reputation_risk": "high",
                "department_code": "front_office",
            },
        ],
    )
    return list(session.scalars(select(NormalizedReview).order_by(NormalizedReview.id)))


def test_review_analysis_fails_clearly_when_sentiment_model_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'sentiment-fallback.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(
        sentiment_module,
        "_load_transformer_pipeline",
        lambda **_: (_ for _ in ()).throw(ImportError("transformers unavailable")),
    )
    get_sentiment_analyzer.cache_clear()
    migrate(database_url)

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            seed_reference_config(session)
            run = run_payload_ingestion(
                session,
                source_code="google_business_profile",
                connector_key="test_sentiment_runtime_failure",
                payloads=[
                    {
                        "source_code": "google_business_profile",
                        "external_review_id": "sentiment-fallback-001",
                        "reviewer_name": "Guest Runtime",
                        "review_date": "2026-05-20T10:00:00+00:00",
                        "rating": 4.0,
                        "language": "en",
                        "title": "Helpful team",
                        "body": "Helpful staff but the queue was slow.",
                    }
                ],
            )

            assert run.status == "failed"
            assert run.error_count == 1
            assert "sentiment runtime unavailable" in run.errors[0]
            assert "nlptown/bert-base-multilingual-uncased-sentiment" in run.errors[0]
            assert session.query(ReviewAnalysis).count() == 0
    finally:
        get_sentiment_analyzer.cache_clear()


def test_review_analysis_uses_local_transformer_sentiment_when_available(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'sentiment-transformer.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    class FakePipeline:
        def __init__(self) -> None:
            self.model = type(
                "FakeModel",
                (),
                {"config": type("FakeConfig", (), {"_commit_hash": "commit-sha-123"})()},
            )()

        def __call__(self, text: str, truncation: bool = True) -> list[dict[str, float | str]]:
            assert truncation is True
            assert text
            return [{"label": "5 stars", "score": 0.91}]

    monkeypatch.setattr(sentiment_module, "_load_transformer_pipeline", lambda **_: FakePipeline())
    get_sentiment_analyzer.cache_clear()
    migrate(database_url)

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            seed_reference_config(session)
            review = _ingest_single_review(session, external_review_id="sentiment-transformer-001")

            assert review.analysis.model_name == "huggingface-transformers-sentiment-analysis"
            assert review.analysis.model_version == "commit-sha-123"
            assert review.analysis.analysis_version == "analysis-v2"
            assert review.analysis.sentiment_label == "positive"
            assert float(review.analysis.sentiment_score) == 1.0
            assert float(review.analysis.sentiment_confidence) == 0.91
            assert review.analysis.explanation_factors["model"]["sentiment_strategy"] == "huggingface_text_classification_pipeline"
            assert review.analysis.explanation_factors["model"]["fallback_note"] is None
    finally:
        get_sentiment_analyzer.cache_clear()


def test_migrations_and_seed_are_repeatable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'config.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url)
    with Session(engine) as session:
        seed_reference_config(session)
        seed_reference_config(session)

        source_codes = set(session.scalars(select(ReviewSource.code)))
        assert source_codes == {"google_business_profile", "booking_com", "tripadvisor"}
        assert set(session.scalars(select(ReviewSource.code))) == {"google_business_profile", "booking_com", "tripadvisor"}
        assert session.query(ReviewSource).count() == 3
        assert session.query(Department).count() == 6
        assert session.query(IssueCategory).count() == 11
        assert session.query(CategoryDepartmentMapping).count() == 12
        assert session.query(ReputationRiskThreshold).count() == 11
        assert session.query(DemoRole).count() == 4

        google = session.get(ReviewSource, "google_business_profile")
        assert google is not None
        assert google.source_metadata["connector_mode"] == "mock_official_shaped"
        assert google.source_metadata["verified_review_source"] is True


def test_seed_ingestion_is_repeatable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'ingestion.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url)
    with Session(engine) as session:
        seed_reference_config(session)

        first_run = run_seed_ingestion(session)
        second_run = run_seed_ingestion(session)

        assert first_run.status == "completed"
        assert first_run.records_seen == 6
        assert first_run.records_created == 6
        assert second_run.status == "completed"
        assert second_run.records_seen == 6
        assert second_run.records_created == 0
        assert second_run.records_skipped == 6
        assert second_run.records_duplicate_flagged == 0
        assert session.query(IngestionRun).count() == 2
        assert session.query(RawReview).count() == 6
        assert session.query(NormalizedReview).count() == 6
        assert all(review.content_hash for review in session.scalars(select(NormalizedReview)))
        assert session.query(ReviewAnalysis).count() == 6
        assert session.query(ReviewIssueCategoryPrediction).count() >= 6

        analyzed_review = session.scalar(
            select(NormalizedReview).where(NormalizedReview.external_review_id == "gbp-seed-005")
        )
        assert analyzed_review is not None
        assert analyzed_review.analysis is not None
        assert analyzed_review.analysis.is_active is True
        assert analyzed_review.analysis.model_name == "huggingface-transformers-sentiment-analysis"
        assert analyzed_review.analysis.model_version == "sentiment-test-revision"
        assert analyzed_review.analysis.analysis_version == "analysis-v2"
        assert analyzed_review.analysis.issue_category_code == "cleanliness"
        assert analyzed_review.analysis.department_code == "housekeeping"
        assert analyzed_review.analysis.reputation_risk_label in {"high", "critical"}
        assert analyzed_review.analysis.explanation_factors["reputation_risk"]["weights"]["rating"] > 0
        assert analyzed_review.analysis.explanation_factors["model"]["fallback_note"] is None
        primary_prediction = analyzed_review.analysis.issue_category_predictions[0]
        assert primary_prediction.category_code == "cleanliness"
        assert primary_prediction.confidence > 0
        assert primary_prediction.model_name == "huggingface-transformers-zero-shot-classification"
        assert primary_prediction.model_version == "issue-test-revision"
        assert primary_prediction.department_code == "housekeeping"
        assert primary_prediction.analyzed_at == analyzed_review.analysis.analyzed_at


def test_ingestion_flags_normalized_content_hash_duplicates(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'content-dedupe.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url)
    with Session(engine) as session:
        seed_reference_config(session)

        payloads = [
            {
                "source_code": "google_business_profile",
                "external_review_id": "dedupe-001",
                "reviewer_name": "Guest One",
                "review_date": "2026-05-20T10:00:00+00:00",
                "rating": 2.0,
                "language": "en",
                "title": "Slow check-in",
                "body": "Check-in queue was very slow.",
                "sentiment_label": "negative",
                "sentiment_score": -0.65,
                "issue_category_code": "booking_checkin",
                "reputation_risk": "high",
                "department_code": "front_office",
            },
            {
                "source_code": "google_business_profile",
                "external_review_id": "dedupe-002",
                "reviewer_name": "Guest Two",
                "review_date": "2026-05-21T12:00:00+00:00",
                "rating": 2,
                "language": "EN",
                "title": "  slow   check-in ",
                "body": " check-in   queue was VERY slow. ",
                "sentiment_label": "negative",
                "sentiment_score": -0.62,
                "issue_category_code": "booking_checkin",
                "reputation_risk": "high",
                "department_code": "front_office",
            },
        ]

        first_run = run_payload_ingestion(
            session,
            source_code="google_business_profile",
            connector_key="test_content_dedupe",
            payloads=payloads,
        )
        second_run = run_payload_ingestion(
            session,
            source_code="google_business_profile",
            connector_key="test_content_dedupe",
            payloads=payloads,
        )

        reviews = list(session.scalars(select(NormalizedReview).order_by(NormalizedReview.id)))

        assert first_run.status == "completed"
        assert first_run.records_created == 2
        assert first_run.records_duplicate_flagged == 2
        assert second_run.records_created == 0
        assert second_run.records_skipped == 2
        assert second_run.records_duplicate_flagged == 2
        assert session.query(RawReview).count() == 2
        assert session.query(NormalizedReview).count() == 2
        assert session.query(ReviewAnalysis).count() == 2
        assert {review.external_review_id for review in reviews} == {"dedupe-001", "dedupe-002"}
        assert len({review.content_hash for review in reviews}) == 1
        assert reviews[0].content_hash == normalized_content_hash(payloads[0])
        assert {review.is_content_duplicate for review in reviews} == {True}
        assert reviews[0].duplicate_of_review_id is None
        assert reviews[1].duplicate_of_review_id == reviews[0].id
        assert all(review.analysis is not None for review in reviews)


def test_semantic_similarity_flags_near_duplicates_without_merging(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'semantic-dedupe.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_semantic_similarity_analyzer.cache_clear()
    migrate(database_url)

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            seed_reference_config(session)

            reviews = _ingest_semantic_reviews(session, connector_key="test_semantic_dedupe")
            semantic_result = analyze_semantic_similarity(reviews)

            assert {review.is_content_duplicate for review in reviews} == {False}
            assert {review.duplicate_of_review_id for review in reviews} == {None}
            assert semantic_result.embedding_strategy in {
                "local_sentence_transformer",
                "tfidf_cosine_fallback",
                "token_overlap_fallback",
            }
            assert semantic_result.near_duplicate_pairs
            assert semantic_result.clusters
            assert semantic_result.clusters[0].size == 2
            assert semantic_result.clusters[0].category_code in {"booking_checkin", "service_delay"}
            assert semantic_result.clusters[0].department_code
            assert semantic_result.clusters[0].source_mix == {"google_business_profile": 2}
    finally:
        get_semantic_similarity_analyzer.cache_clear()


def test_semantic_similarity_uses_sentence_transformer_when_available(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'semantic-transformer.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    class FakeSentenceTransformer:
        revision = "local-mini-lm-revision"

        def encode(self, texts: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
            assert normalize_embeddings is True
            assert len(texts) == 2
            return [
                [1.0, 0.0, 0.0],
                [0.92, 0.08, 0.0],
            ]

    monkeypatch.setattr(
        semantic_similarity_module,
        "_load_sentence_transformer",
        lambda **_: FakeSentenceTransformer(),
    )
    get_semantic_similarity_analyzer.cache_clear()
    migrate(database_url)

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            seed_reference_config(session)
            reviews = _ingest_semantic_reviews(session, connector_key="test_semantic_transformer")
            semantic_result = analyze_semantic_similarity(reviews)

            assert semantic_result.embedding_strategy == "local_sentence_transformer"
            assert semantic_result.embedding_model_name == "local-sentence-transformer-review-embeddings"
            assert semantic_result.embedding_model_version == "local-mini-lm-revision"
            assert "TF-IDF cosine similarity" in semantic_result.embedding_fallback_note
            assert semantic_result.near_duplicate_pairs
            assert semantic_result.clusters
    finally:
        get_semantic_similarity_analyzer.cache_clear()


def test_semantic_similarity_uses_tfidf_fallback_metadata_when_transformer_unavailable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'semantic-tfidf-fallback.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(
        semantic_similarity_module,
        "_load_sentence_transformer",
        lambda **_: (_ for _ in ()).throw(ImportError("sentence-transformers unavailable")),
    )
    get_semantic_similarity_analyzer.cache_clear()
    migrate(database_url)

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            seed_reference_config(session)
            reviews = _ingest_semantic_reviews(session, connector_key="test_semantic_tfidf_fallback")
            semantic_result = analyze_semantic_similarity(reviews, similarity_threshold=0.30)

            assert semantic_result.embedding_strategy == "tfidf_cosine_fallback"
            assert semantic_result.embedding_model_name == "local-tfidf-cosine-review-embeddings"
            assert "sentence-transformers unavailable" in semantic_result.embedding_fallback_note
            assert semantic_result.clusters
    finally:
        get_semantic_similarity_analyzer.cache_clear()


def test_recurring_issue_and_semantic_cluster_tickets_reuse_ticket_lifecycle(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'recurring-ticket.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_reference_config(session)
        run_payload_ingestion(
            session,
            source_code="google_business_profile",
            connector_key="test_recurring_issue_ticket",
            payloads=[
                {
                    "source_code": "google_business_profile",
                    "external_review_id": "recurring-001",
                    "reviewer_name": "Guest One",
                    "review_date": "2026-05-20T10:00:00+00:00",
                    "rating": 2.0,
                    "language": "en",
                    "title": "Slow check-in queue",
                    "body": "The front desk check-in queue was very slow and took too long.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.65,
                    "issue_category_code": "booking_checkin",
                    "reputation_risk": "high",
                    "department_code": "front_office",
                },
                {
                    "source_code": "google_business_profile",
                    "external_review_id": "recurring-002",
                    "reviewer_name": "Guest Two",
                    "review_date": "2026-05-21T12:00:00+00:00",
                    "rating": 2.0,
                    "language": "en",
                    "title": "Front desk delay",
                    "body": "Check-in at the front desk took a very long time because the queue was slow.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.62,
                    "issue_category_code": "booking_checkin",
                    "reputation_risk": "high",
                    "department_code": "front_office",
                },
            ],
        )

    def override_get_session():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        initial_summary_response = client.get("/issues/summary")
        summary_item = initial_summary_response.json()["items"][0]
        category_code = summary_item["category_code"]
        department_code = summary_item["department_code"]
        category_response = client.post(
            f"/issues/groups/{category_code}/{department_code}/tickets",
            json={"priority": "high", "notes": "Repeated arrival friction."},
        )
        summary_response = client.get("/issues/summary")
        semantic_response = client.get("/analysis/semantic-clusters", params={"similarity_threshold": 0.30})
        cluster_id = semantic_response.json()["clusters"][0]["cluster_id"]
        cluster_response = client.post(
            f"/analysis/semantic-clusters/{cluster_id}/tickets",
            params={"similarity_threshold": 0.30},
            json={"priority": "urgent", "notes": "Clustered check-in delays."},
        )
        tickets_response = client.get("/tickets", params={"issue_category_code": category_code})
        all_tickets_response = client.get("/tickets")
    finally:
        app.dependency_overrides.clear()

    assert category_response.status_code == 201
    category_ticket = category_response.json()
    assert category_ticket["review_id"] is None
    assert category_ticket["department_code"] == department_code
    assert category_ticket["source_group_type"] == "category_department_recurrence"
    assert category_ticket["source_group_key"] == f"{category_code}:{department_code}"
    assert category_ticket["source_category_code"] == category_code
    assert len(category_ticket["source_review_ids"]) == 2
    assert category_ticket["events"][0]["event_type"] == "created"

    assert initial_summary_response.status_code == 200
    assert summary_response.status_code == 200
    booking_summary = next(
        item
        for item in summary_response.json()["items"]
        if item["category_code"] == category_code and item["department_code"] == department_code
    )
    assert category_ticket["id"] in booking_summary["linked_ticket_ids"]
    assert booking_summary["recent_review_count"] == 2
    assert booking_summary["review_count"] == 2
    assert booking_summary["highest_reputation_risk"] == "high"
    assert booking_summary["source_mix"] == {"google_business_profile": 2}

    assert semantic_response.status_code == 200
    assert semantic_response.json()["clusters"]
    assert cluster_response.status_code == 201
    cluster_ticket = cluster_response.json()
    assert cluster_ticket["source_group_type"] == "semantic_cluster"
    assert cluster_ticket["source_cluster_id"] == cluster_id
    assert cluster_ticket["source_category_code"] in {"booking_checkin", "service_delay"}
    assert len(cluster_ticket["source_review_ids"]) == 2

    assert tickets_response.status_code == 200
    ticket_ids = {ticket["id"] for ticket in tickets_response.json()["tickets"]}
    assert category_ticket["id"] in ticket_ids
    assert all_tickets_response.status_code == 200
    all_ticket_ids = {ticket["id"] for ticket in all_tickets_response.json()["tickets"]}
    assert {category_ticket["id"], cluster_ticket["id"]} <= all_ticket_ids

    with TestingSessionLocal() as session:
        assert session.query(ActionTicket).count() == 2
        assert session.query(TicketEvent).count() == 2
        assert {review.action_status for review in session.scalars(select(NormalizedReview))} == {"ticket_created"}


def test_issue_summary_groups_recent_reviews_by_category_and_department(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'issue-summary-groups.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_reference_config(session)
        run_payload_ingestion(
            session,
            source_code="google_business_profile",
            connector_key="test_issue_summary_groups",
            payloads=[
                {
                    "source_code": "google_business_profile",
                    "external_review_id": "front-desk-001",
                    "reviewer_name": "Guest One",
                    "review_date": "2026-05-20T10:00:00+00:00",
                    "rating": 2.0,
                    "language": "en",
                    "title": "Slow front desk",
                    "body": "Check-in at the front desk was slow and the queue moved badly.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.62,
                    "issue_category_code": "booking_checkin",
                    "reputation_risk": "high",
                    "department_code": "front_office",
                },
            ],
        )
        run_payload_ingestion(
            session,
            source_code="booking_com",
            connector_key="test_issue_summary_groups_booking",
            payloads=[
                {
                    "source_code": "booking_com",
                    "external_review_id": "front-desk-002",
                    "reviewer_name": "Guest Two",
                    "review_date": "2026-05-19T10:00:00+00:00",
                    "rating": 2.0,
                    "language": "en",
                    "title": "Arrival queue",
                    "body": "The booking was fine but check-in had a long queue and slow service.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.55,
                    "issue_category_code": "booking_checkin",
                    "reputation_risk": "high",
                    "department_code": "front_office",
                },
            ],
        )
        run_payload_ingestion(
            session,
            source_code="tripadvisor",
            connector_key="test_issue_summary_groups_tripadvisor",
            payloads=[
                {
                    "source_code": "tripadvisor",
                    "external_review_id": "service-delay-001",
                    "reviewer_name": "Guest Three",
                    "review_date": "2026-05-01T10:00:00+00:00",
                    "rating": 3.0,
                    "language": "en",
                    "title": "Slow response",
                    "body": "Requests took too long and staff follow-up was delayed.",
                    "sentiment_label": "mixed",
                    "sentiment_score": -0.18,
                    "issue_category_code": "service_delay",
                    "reputation_risk": "medium",
                    "department_code": "guest_relations",
                },
            ],
        )

    def override_get_session():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        summary_response = client.get("/issues/summary")
    finally:
        app.dependency_overrides.clear()

    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["total_reviews"] == 3
    assert len(payload["items"]) == 2

    front_office_group = next(
        item
        for item in payload["items"]
        if item["category_code"] == "booking_checkin" and item["department_code"] == "front_office"
    )
    assert front_office_group["group_key"] == "booking_checkin:front_office"
    assert front_office_group["review_count"] == 2
    assert front_office_group["recent_review_count"] == 2
    assert front_office_group["highest_reputation_risk"] == "high"
    assert front_office_group["average_reputation_risk_score"] >= 50
    assert front_office_group["source_mix"] == {
        "google_business_profile": 1,
        "booking_com": 1,
    }

    guest_relations_group = next(
        item
        for item in payload["items"]
        if item["category_code"] == "service_delay" and item["department_code"] == "guest_relations"
    )
    assert guest_relations_group["review_count"] == 1
    assert guest_relations_group["recent_review_count"] == 0
    assert guest_relations_group["highest_reputation_risk"] == "medium"


def test_verified_mock_connectors_are_independently_repeatable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'verified-connectors.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url)
    with Session(engine) as session:
        seed_reference_config(session)

        for connector_key, connector in CONNECTORS.items():
            assert "mock_analysis" not in json.dumps(connector.records)
            first_run = run_mock_connector_by_key(session, connector_key)
            second_run = run_mock_connector_by_key(session, connector_key)

            assert first_run.status == "completed"
            assert first_run.records_seen == 2
            assert first_run.records_created == 2
            assert second_run.status == "completed"
            assert second_run.records_seen == 2
            assert second_run.records_created == 0
            assert second_run.records_skipped == 2

        assert session.query(IngestionRun).count() == 6
        assert session.query(RawReview).count() == 6
        assert session.query(NormalizedReview).count() == 6
        assert session.query(ReviewAnalysis).count() == 6
        raw_google = session.scalar(select(RawReview).where(RawReview.source_code == "google_business_profile"))
        assert raw_google is not None
        assert "reviewId" in raw_google.raw_payload
        assert "mock_analysis" not in json.dumps(raw_google.raw_payload)
        normalized_google = session.scalar(
            select(NormalizedReview).where(NormalizedReview.source_code == "google_business_profile")
        )
        assert normalized_google is not None
        assert normalized_google.normalized_payload["verified_review_source"] is True
        assert normalized_google.normalized_payload["mock_official_shaped_connector"] is True
        assert normalized_google.analysis is not None
        assert normalized_google.analysis.explanation_factors["department"]["mapping_source"] == "category_department_mappings.primary"
        assert normalized_google.sentiment_label != "pending"


def test_verified_connector_normalizers_only_emit_review_fields_and_platform_metadata() -> None:
    analysis_fields = {
        "sentiment_label",
        "sentiment_score",
        "issue_category_code",
        "reputation_risk",
        "department_code",
        "mock_analysis",
    }

    for connector in CONNECTORS.values():
        normalized = connector.normalize(connector.records[0])
        assert {"source_code", "external_review_id", "body", "normalized_payload"} <= set(normalized)
        assert analysis_fields.isdisjoint(normalized)
        assert analysis_fields.isdisjoint(normalized["normalized_payload"])


def test_verified_connector_fixture_files_run_through_shared_ingestion_path(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'verified-connector-fixtures.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url)
    with Session(engine) as session:
        seed_reference_config(session)

        for connector_key, connector in CONNECTORS.items():
            fixture_path = tmp_path / f"{connector_key}.json"
            fixture_path.write_text(json.dumps(list(connector.records), indent=2), encoding="utf-8")

            first_run = run_mock_connector_by_key(session, connector_key, fixture_path=fixture_path)
            second_run = run_mock_connector_by_key(session, connector_key, fixture_path=fixture_path)

            assert first_run.connector_key == connector_key
            assert first_run.source_code == connector.source_code
            assert first_run.status == "completed"
            assert first_run.records_seen == len(connector.records)
            assert first_run.records_created == len(connector.records)
            assert second_run.status == "completed"
            assert second_run.records_skipped == len(connector.records)

        imported_reviews = list(session.scalars(select(NormalizedReview).order_by(NormalizedReview.id)))
        assert len(imported_reviews) == 6
        assert all(review.analysis is not None for review in imported_reviews)
        assert all(review.sentiment_label != "pending" for review in imported_reviews)
        assert all("mock_analysis" not in json.dumps(review.raw_review.raw_payload) for review in imported_reviews)


def test_api_endpoints_expose_only_review_platform_sources_and_filters(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'api-config.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_reference_config(session)
        run_seed_ingestion(session)
    fixture_path = tmp_path / "google_business_profile-fixture.json"
    fixture_path.write_text(json.dumps(list(CONNECTORS["google_business_profile"].records), indent=2), encoding="utf-8")

    def override_get_session():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        config_response = client.get("/config")
        reviews_response = client.get("/reviews")
        source_filtered_response = client.get("/reviews", params={"source_code": "google_business_profile"})
        cleanliness_reviews_response = client.get("/reviews", params={"issue_category_code": "cleanliness"})
        housekeeping_reviews_response = client.get("/reviews", params={"department_code": "housekeeping"})
        semantic_response = client.get("/analysis/semantic-clusters", params={"similarity_threshold": 0.30})
        runs_response = client.get("/ingestion/runs")
        reanalysis_response = client.post("/analysis/reanalyze")
        connector_response = client.post(
            "/ingestion/connectors/google_business_profile",
            json={"fixture_path": str(fixture_path)},
        )
        repeat_connector_response = client.post(
            "/ingestion/connectors/google_business_profile",
            json={"fixture_path": str(fixture_path)},
        )
        source_status_response = client.get("/ingestion/source-status")
        openapi_response = client.get("/openapi.json")
        removed_seed_response = client.post("/ingestion/seed")
        removed_reddit_response = client.post("/ingestion/reddit")
        removed_apify_response = client.post("/ingestion/apify-dataset", json={})
    finally:
        app.dependency_overrides.clear()

    assert config_response.status_code == 200
    payload = config_response.json()
    assert {source["code"] for source in payload["review_sources"]} == {
        "google_business_profile",
        "booking_com",
        "tripadvisor",
    }
    assert all("source_type" not in source for source in payload["review_sources"])
    assert payload["review_sources"][0]["metadata"] is not None
    assert len(payload["departments"]) == 6
    assert len(payload["issue_categories"]) == 11
    assert len(payload["category_department_mappings"]) == 12
    assert len(payload["reputation_risk_thresholds"]) == 11
    assert len(payload["demo_roles"]) == 4

    assert reviews_response.status_code == 200
    default_reviews = reviews_response.json()["reviews"]
    assert len(default_reviews) == 6
    assert {review["source_code"] for review in default_reviews} == {"google_business_profile"}
    assert all("source_type" not in review for review in default_reviews)
    assert all(review["analysis"] is not None for review in default_reviews)
    assert all(review["analysis"]["reputation_risk_score"] >= 0 for review in default_reviews)
    assert all("model_name" not in review["analysis"] for review in default_reviews)
    assert all("model_version" not in review["analysis"] for review in default_reviews)
    assert all("analysis_version" not in review["analysis"] for review in default_reviews)
    assert all("model" not in review["analysis"]["explanation_factors"] for review in default_reviews)
    assert all("reputation_risk" in review["analysis"]["explanation_factors"] for review in default_reviews)
    assert all(review["analysis"]["issue_category_predictions"] for review in default_reviews)
    assert all(
        {"category_code", "confidence", "analyzed_at"}
        <= set(review["analysis"]["issue_category_predictions"][0])
        for review in default_reviews
    )
    assert all("model_name" not in review["analysis"]["issue_category_predictions"][0] for review in default_reviews)
    assert all("model_version" not in review["analysis"]["issue_category_predictions"][0] for review in default_reviews)

    assert source_filtered_response.status_code == 200
    assert {review["source_code"] for review in source_filtered_response.json()["reviews"]} == {"google_business_profile"}
    assert cleanliness_reviews_response.status_code == 200
    assert len(cleanliness_reviews_response.json()["reviews"]) >= 1
    assert housekeeping_reviews_response.status_code == 200
    assert len(housekeeping_reviews_response.json()["reviews"]) >= 1
    assert semantic_response.status_code == 200
    semantic_payload = semantic_response.json()
    assert semantic_payload["embedding_strategy"] in {
        "local_sentence_transformer",
        "tfidf_cosine_fallback",
        "token_overlap_fallback",
    }
    assert semantic_payload["embedding_model_name"] in {
        "local-sentence-transformer-review-embeddings",
        "local-tfidf-cosine-review-embeddings",
        "local-token-overlap-review-embeddings",
    }
    assert semantic_payload["similarity_threshold"] == 0.30
    assert semantic_payload["embedding_fallback_note"]
    assert "near_duplicate_pairs" in semantic_payload
    assert "clusters" in semantic_payload
    assert runs_response.status_code == 200
    assert len(runs_response.json()["runs"]) == 1
    assert reanalysis_response.status_code == 200
    assert reanalysis_response.json()["analyzed_count"] == 6
    assert connector_response.status_code == 200
    assert connector_response.json()["records_created"] == 2
    assert repeat_connector_response.status_code == 200
    assert repeat_connector_response.json()["records_skipped"] == 2
    assert source_status_response.status_code == 200
    source_statuses = source_status_response.json()["sources"]
    assert {source["source_code"] for source in source_statuses} == {
        "google_business_profile",
        "booking_com",
        "tripadvisor",
    }
    assert all("source_type" not in source for source in source_statuses)
    google_status = next(source for source in source_statuses if source["source_code"] == "google_business_profile")
    assert google_status["is_verified_channel"] is True
    assert google_status["latest_run"]["status"] == "completed"
    assert google_status["errors"] == []

    assert openapi_response.status_code == 200
    openapi_paths = openapi_response.json()["paths"]
    assert "/ingestion/seed" not in openapi_paths
    assert "/ingestion/reddit" not in openapi_paths
    assert "/ingestion/apify-dataset" not in openapi_paths
    for path in ("/reviews", "/overview/kpis", "/issues/summary", "/analysis/semantic-clusters"):
        get_params = openapi_paths[path]["get"].get("parameters", [])
        parameter_names = {parameter["name"] for parameter in get_params}
        assert "source_type" not in parameter_names
        assert "include_social_listening" not in parameter_names
    assert removed_seed_response.status_code == 404
    assert removed_reddit_response.status_code == 404
    assert removed_apify_response.status_code == 404


def test_connector_api_returns_503_when_required_issue_model_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'api-analysis-failure.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_reference_config(session)

    fixture_path = tmp_path / "google_business_profile-fixture.json"
    fixture_path.write_text(json.dumps(list(CONNECTORS["google_business_profile"].records), indent=2), encoding="utf-8")

    def override_get_session():
        with TestingSessionLocal() as session:
            yield session

    monkeypatch.setattr(
        issue_classifier_module,
        "_load_transformer_pipeline",
        lambda **_: (_ for _ in ()).throw(FileNotFoundError("missing local bart model")),
    )
    get_issue_category_classifier.cache_clear()
    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        connector_response = client.post(
            "/ingestion/connectors/google_business_profile",
            json={"fixture_path": str(fixture_path)},
        )
    finally:
        app.dependency_overrides.clear()
        get_issue_category_classifier.cache_clear()

    assert connector_response.status_code == 503
    assert "issue-category runtime unavailable" in connector_response.json()["detail"]
    assert "facebook/bart-large-mnli" in connector_response.json()["detail"]


def test_review_api_searches_filters_and_redacts_display_fields(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'review-search-redaction.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_reference_config(session)
        run_payload_ingestion(
            session,
            source_code="google_business_profile",
            connector_key="test_search_redaction",
            payloads=[
                {
                    "source_code": "google_business_profile",
                    "external_review_id": "private-guest-001",
                    "reviewer_name": "guest@example.com",
                    "review_date": "2026-05-20T10:00:00+00:00",
                    "rating": 2.0,
                    "language": "en",
                    "title": "Call me on +94 77 123 4567",
                    "body": "Room was dirty. Email me at guest@example.com about the broken shower.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.65,
                    "issue_category_code": "cleanliness",
                    "reputation_risk": "high",
                    "department_code": "housekeeping",
                },
                {
                    "source_code": "google_business_profile",
                    "external_review_id": "quiet-positive-001",
                    "reviewer_name": "Public Guest",
                    "review_date": "2026-05-21T10:00:00+00:00",
                    "rating": 5.0,
                    "language": "en",
                    "title": "Helpful team",
                    "body": "Excellent staff and smooth check-in.",
                    "sentiment_label": "positive",
                    "sentiment_score": 0.75,
                    "issue_category_code": "positive_general",
                    "reputation_risk": "low",
                    "department_code": "guest_relations",
                },
            ],
        )

    def override_get_session():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        search_response = client.get("/reviews", params={"search": "guest@example.com"})
        filtered_search_response = client.get(
            "/reviews",
            params={"search": "broken shower", "department_code": "housekeeping"},
        )
        paginated_response = client.get("/reviews", params={"per_page": 1, "page": 2})
        no_match_response = client.get(
            "/reviews",
            params={"search": "broken shower", "department_code": "front_office"},
        )
    finally:
        app.dependency_overrides.clear()

    assert search_response.status_code == 200
    search_reviews = search_response.json()["reviews"]
    assert len(search_reviews) == 1
    private_review = search_reviews[0]
    assert private_review["reviewer_name"] == "guest@example.com"
    assert private_review["body"] == "Room was dirty. Email me at guest@example.com about the broken shower."
    assert private_review["display_reviewer_name"] == "[redacted email]"
    assert private_review["display_title"] == "Call me on [redacted phone]"
    assert private_review["display_body"] == "Room was dirty. Email me at [redacted email] about the broken shower."
    assert private_review["has_display_redactions"] is True
    assert set(private_review["redacted_display_fields"]) == {"reviewer_name", "title", "body"}

    assert filtered_search_response.status_code == 200
    assert [review["external_review_id"] for review in filtered_search_response.json()["reviews"]] == ["private-guest-001"]
    assert paginated_response.status_code == 200
    paginated_payload = paginated_response.json()
    assert paginated_payload["total"] == 2
    assert paginated_payload["page"] == 2
    assert paginated_payload["per_page"] == 1
    assert paginated_payload["total_pages"] == 2
    assert len(paginated_payload["reviews"]) == 1
    assert no_match_response.status_code == 200
    assert no_match_response.json()["reviews"] == []

    with TestingSessionLocal() as session:
        raw_review = session.scalar(select(RawReview).where(RawReview.external_review_id == "private-guest-001"))
        assert raw_review is not None
        assert raw_review.raw_payload["reviewer_name"] == "guest@example.com"
        normalized_review = session.scalar(
            select(NormalizedReview).where(NormalizedReview.external_review_id == "private-guest-001")
        )
        assert normalized_review is not None
        assert normalized_review.reviewer_name == "guest@example.com"


def test_review_api_can_order_by_operational_priority(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'review-priority-order.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_reference_config(session)
        run_payload_ingestion(
            session,
            source_code="google_business_profile",
            connector_key="test_priority_order",
            payloads=[
                {
                    "source_code": "google_business_profile",
                    "external_review_id": "recent-low-001",
                    "reviewer_name": "Recent Guest",
                    "review_date": "2026-05-22T10:00:00+00:00",
                    "rating": 5.0,
                    "language": "en",
                    "title": "Helpful team",
                    "body": "Excellent staff and smooth check-in.",
                    "sentiment_label": "positive",
                    "sentiment_score": 0.75,
                    "issue_category_code": "positive_general",
                    "reputation_risk": "low",
                    "department_code": "guest_relations",
                },
                {
                    "source_code": "google_business_profile",
                    "external_review_id": "older-high-ticket-001",
                    "reviewer_name": "Ticketed Guest",
                    "review_date": "2026-05-18T10:00:00+00:00",
                    "rating": 2.0,
                    "language": "en",
                    "title": "Slow check-in",
                    "body": "The check-in queue took a long time.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.55,
                    "issue_category_code": "booking_checkin",
                    "reputation_risk": "high",
                    "department_code": "front_office",
                },
                {
                    "source_code": "google_business_profile",
                    "external_review_id": "older-high-new-001",
                    "reviewer_name": "Waiting Guest",
                    "review_date": "2026-05-17T10:00:00+00:00",
                    "rating": 1.0,
                    "language": "en",
                    "title": "Broken room fixture",
                    "body": "The shower fixture was broken and nobody followed up.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.85,
                    "issue_category_code": "room_condition",
                    "reputation_risk": "high",
                    "department_code": "engineering",
                },
            ],
        )
        ticketed_review = session.scalar(
            select(NormalizedReview).where(NormalizedReview.external_review_id == "older-high-ticket-001")
        )
        assert ticketed_review is not None
        ticketed_review.action_status = "ticket_created"
        session.commit()

    def override_get_session():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        priority_response = client.get("/reviews", params={"order_by": "operational_priority"})
        recent_response = client.get("/reviews")
        invalid_response = client.get("/reviews", params={"order_by": "rating"})
    finally:
        app.dependency_overrides.clear()

    assert priority_response.status_code == 200
    assert [review["external_review_id"] for review in priority_response.json()["reviews"]] == [
        "older-high-new-001",
        "older-high-ticket-001",
        "recent-low-001",
    ]
    assert recent_response.status_code == 200
    assert recent_response.json()["reviews"][0]["external_review_id"] == "recent-low-001"
    assert invalid_response.status_code == 422


def test_dashboard_action_analytics_and_group_filters(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'dashboard-action-analytics.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_reference_config(session)
        run_payload_ingestion(
            session,
            source_code="google_business_profile",
            connector_key="dashboard-analytics-google",
            payloads=[
                {
                    "source_code": "google_business_profile",
                    "external_review_id": "fo-high-new-001",
                    "reviewer_name": "Guest One",
                    "review_date": "2026-05-25T10:00:00+00:00",
                    "rating": 2.0,
                    "language": "en",
                    "title": "Front desk delay",
                    "body": "Check-in was slow and the queue barely moved.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.61,
                    "issue_category_code": "booking_checkin",
                    "reputation_risk": "high",
                    "department_code": "front_office",
                },
                {
                    "source_code": "google_business_profile",
                    "external_review_id": "housekeeping-ticketed-001",
                    "reviewer_name": "Guest Two",
                    "review_date": "2026-05-20T10:00:00+00:00",
                    "rating": 2.0,
                    "language": "en",
                    "title": "Dirty bathroom",
                    "body": "The bathroom was dirty and housekeeping missed it.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.70,
                    "issue_category_code": "cleanliness",
                    "reputation_risk": "high",
                    "department_code": "housekeeping",
                },
            ],
        )
        run_payload_ingestion(
            session,
            source_code="booking_com",
            connector_key="dashboard-analytics-booking",
            payloads=[
                {
                    "source_code": "booking_com",
                    "external_review_id": "fo-critical-reviewed-001",
                    "reviewer_name": "Guest Three",
                    "review_date": "2026-05-24T10:00:00+00:00",
                    "rating": 1.0,
                    "language": "en",
                    "title": "Arrival was chaotic",
                    "body": "The arrival queue was chaotic and staff were overwhelmed.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.88,
                    "issue_category_code": "booking_checkin",
                    "reputation_risk": "critical",
                    "department_code": "front_office",
                },
                {
                    "source_code": "booking_com",
                    "external_review_id": "engineering-critical-new-001",
                    "reviewer_name": "Guest Four",
                    "review_date": "2026-05-10T10:00:00+00:00",
                    "rating": 1.0,
                    "language": "en",
                    "title": "Broken air conditioning",
                    "body": "The room air conditioning was broken and never fixed.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.91,
                    "issue_category_code": "room_condition",
                    "reputation_risk": "critical",
                    "department_code": "engineering",
                },
                {
                    "source_code": "booking_com",
                    "external_review_id": "positive-low-001",
                    "reviewer_name": "Guest Five",
                    "review_date": "2026-05-26T10:00:00+00:00",
                    "rating": 5.0,
                    "language": "en",
                    "title": "Great service",
                    "body": "Everything was smooth and the team was kind.",
                    "sentiment_label": "positive",
                    "sentiment_score": 0.82,
                    "issue_category_code": "positive_general",
                    "reputation_risk": "low",
                    "department_code": "guest_relations",
                },
            ],
        )
        run_payload_ingestion(
            session,
            source_code="tripadvisor",
            connector_key="dashboard-analytics-tripadvisor",
            payloads=[
                {
                    "source_code": "tripadvisor",
                    "external_review_id": "service-delay-high-new-001",
                    "reviewer_name": "Guest Six",
                    "review_date": "2026-05-18T10:00:00+00:00",
                    "rating": 2.0,
                    "language": "en",
                    "title": "Requests took too long",
                    "body": "Room service requests took too long and nobody followed up.",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.67,
                    "issue_category_code": "service_delay",
                    "reputation_risk": "high",
                    "department_code": "guest_relations",
                },
            ],
        )

        intended_fields = {
            "fo-high-new-001": ("booking_checkin", "front_office", "high"),
            "housekeeping-ticketed-001": ("cleanliness", "housekeeping", "high"),
            "fo-critical-reviewed-001": ("booking_checkin", "front_office", "critical"),
            "engineering-critical-new-001": ("room_condition", "engineering", "critical"),
            "positive-low-001": ("positive_general", "guest_relations", "low"),
            "service-delay-high-new-001": ("service_delay", "guest_relations", "high"),
        }
        for external_review_id, (category_code, department_code, risk_label) in intended_fields.items():
            review = session.scalar(
                select(NormalizedReview).where(NormalizedReview.external_review_id == external_review_id)
            )
            assert review is not None
            review.issue_category_code = category_code
            review.department_code = department_code
            review.reputation_risk = risk_label
            if review.analysis is not None:
                review.analysis.issue_category_code = category_code
                review.analysis.department_code = department_code
                review.analysis.reputation_risk_label = risk_label

        ticketed_review = session.scalar(
            select(NormalizedReview).where(NormalizedReview.external_review_id == "housekeeping-ticketed-001")
        )
        assert ticketed_review is not None
        ticketed_review.action_status = "ticket_created"
        now = datetime.now(UTC)
        ticket = ActionTicket(
            review_id=ticketed_review.id,
            department_code=ticketed_review.department_code,
            source_group_type=None,
            source_group_key=None,
            source_group_label=None,
            source_category_code=None,
            source_cluster_id=None,
            source_review_ids=None,
            priority="high",
            status="open",
            assignee_name=None,
            assignee_email=None,
            due_date=None,
            notes="Created from high-risk review.",
            created_at=now,
            updated_at=now,
        )
        session.add(ticket)
        session.flush()
        session.add(
            TicketEvent(
                ticket_id=ticket.id,
                event_type="created",
                old_value=None,
                new_value="open",
                note="Created from high-risk review.",
                occurred_at=now,
            )
        )
        reviewed_review = session.scalar(
            select(NormalizedReview).where(NormalizedReview.external_review_id == "fo-critical-reviewed-001")
        )
        assert reviewed_review is not None
        reviewed_review.action_status = "reviewed"
        session.commit()

    def override_get_session():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        high_risk_reviews_response = client.get("/reviews", params={"risk_group": "high_or_critical"})
        ticket_needed_reviews_response = client.get(
            "/reviews",
            params={"risk_group": "high_or_critical", "action_status_group": "ticket_needed"},
        )
        front_office_issues_response = client.get(
            "/issues/summary",
            params={"department_code": "front_office", "risk_group": "high_or_critical"},
        )
        action_analytics_response = client.get("/overview/action-analytics")
    finally:
        app.dependency_overrides.clear()

    assert high_risk_reviews_response.status_code == 200
    assert {
        review["external_review_id"] for review in high_risk_reviews_response.json()["reviews"]
    } == {
        "fo-high-new-001",
        "housekeeping-ticketed-001",
        "fo-critical-reviewed-001",
        "engineering-critical-new-001",
        "service-delay-high-new-001",
    }

    assert ticket_needed_reviews_response.status_code == 200
    assert {
        review["external_review_id"] for review in ticket_needed_reviews_response.json()["reviews"]
    } == {
        "fo-high-new-001",
        "fo-critical-reviewed-001",
        "engineering-critical-new-001",
        "service-delay-high-new-001",
    }

    assert front_office_issues_response.status_code == 200
    front_office_items = front_office_issues_response.json()["items"]
    assert any(item["group_key"] == "booking_checkin:front_office" for item in front_office_items)

    assert action_analytics_response.status_code == 200
    payload = action_analytics_response.json()
    assert payload["high_risk_reviews"]["review_count"] == 5
    assert payload["high_risk_reviews"]["drill_through"] == {
        "path": "/reviews",
        "filters": {"risk_group": "high_or_critical"},
    }
    assert payload["action_leakage"]["review_count"] == 4
    assert payload["action_leakage"]["drill_through"]["filters"] == {
        "risk_group": "high_or_critical",
        "action_status_group": "ticket_needed",
    }
    assert payload["aging_risk"]["review_count"] == 1
    assert payload["aging_risk"]["threshold_days"] == 7
    assert payload["aging_risk"]["oldest_review_date"].startswith("2026-05-10")

    assert payload["owner_pressure"][0]["department_code"] == "front_office"
    assert payload["owner_pressure"][0]["unresolved_high_risk_reviews"] == 2
    assert payload["owner_pressure"][0]["recurring_issue_groups"] == 1
    assert payload["owner_pressure"][0]["issues_drill_through"]["filters"] == {
        "department_code": "front_office",
        "risk_group": "high_or_critical",
    }

    assert payload["platform_risk_spread"][0]["source_code"] == "booking_com"
    assert payload["platform_risk_spread"][0]["high_risk_reviews"] == 2
    assert payload["platform_risk_spread"][0]["ticket_needed_reviews"] == 2

    assert len(payload["recurring_issues_without_tickets"]) == 1
    recurring_issue = payload["recurring_issues_without_tickets"][0]
    assert recurring_issue["group_key"] == "booking_checkin:front_office"
    assert recurring_issue["review_count"] == 2
    assert recurring_issue["linked_ticket_ids"] == []
    assert recurring_issue["issues_drill_through"]["filters"] == {
        "issue_category_code": "booking_checkin",
        "department_code": "front_office",
    }


def test_ticket_update_api_records_manageable_field_events(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'ticket-update.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_reference_config(session)
        run_seed_ingestion(session)

    def override_get_session():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        reviews_response = client.get("/reviews")
        high_risk_review = next(
            review
            for review in reviews_response.json()["reviews"]
            if review["analysis"]["reputation_risk_label"] in {"high", "critical"}
        )
        default_priority_response = client.post(
            f"/reviews/{high_risk_review['id']}/tickets",
            json={"department_code": high_risk_review["department_code"], "notes": "Default from Reputation Risk."},
        )
        create_response = client.post(
            "/reviews/1/tickets",
            json={"department_code": "housekeeping", "priority": "medium", "notes": "Initial review."},
        )
        ticket_id = create_response.json()["id"]
        premature_verify_response = client.patch(
            f"/tickets/{ticket_id}",
            json={"status": "verified"},
        )
        update_response = client.patch(
            f"/tickets/{ticket_id}",
            json={
                "status": "resolved",
                "priority": "urgent",
                "department_code": "guest_relations",
                "assignee_name": "Ops Manager",
                "due_date": "2026-05-30T00:00:00+00:00",
                "notes": "Resolution completed.",
            },
        )
        clear_assignment_response = client.patch(
            f"/tickets/{ticket_id}",
            json={"assignee_name": None, "assignee_email": None, "due_date": None},
        )
        verify_response = client.patch(
            f"/tickets/{ticket_id}",
            json={"status": "verified", "notes": "Management verified."},
        )
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 201
    assert default_priority_response.status_code == 201
    expected_priority = "urgent" if high_risk_review["analysis"]["reputation_risk_label"] == "critical" else "high"
    assert default_priority_response.json()["priority"] == expected_priority
    assert premature_verify_response.status_code == 422
    assert premature_verify_response.json()["detail"] == "Cannot transition ticket from open to verified"
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["status"] == "resolved"
    assert updated["priority"] == "urgent"
    assert updated["department_code"] == "guest_relations"
    assert updated["assignee_name"] == "Ops Manager"
    update_event_types = {event["event_type"] for event in updated["events"]}
    assert {"status_change", "priority_change", "department_change", "assignment_change", "due_date_change", "note_added"} <= update_event_types

    assert clear_assignment_response.status_code == 200
    cleared = clear_assignment_response.json()
    assert cleared["assignee_name"] is None
    assert cleared["assignee_email"] is None
    assert cleared["due_date"] is None
    assert any(
        event["event_type"] == "assignment_change" and event["old_value"] == "Ops Manager" and event["new_value"] is None
        for event in cleared["events"]
    )
    assert any(
        event["event_type"] == "due_date_change" and event["new_value"] is None
        for event in cleared["events"]
    )

    assert verify_response.status_code == 200
    verified = verify_response.json()
    assert verified["status"] == "verified"
    assert any(event["event_type"] == "status_change" and event["new_value"] == "verified" for event in verified["events"])
    assert any(event["event_type"] == "note_added" and event["note"] == "Management verified." for event in verified["events"])
