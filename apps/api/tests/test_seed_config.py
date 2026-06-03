from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.apify_importer import ApifyImportInput, run_apify_dataset_import
from app import sentiment as sentiment_module
from app.connectors.registry import CONNECTORS
from app.database import get_session
from app.ingestion import normalized_content_hash, run_mock_connector_by_key, run_payload_ingestion, run_seed_ingestion
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
    SeverityThreshold,
    TicketEvent,
)
from app.reddit_import import run_reddit_social_listening_ingestion
from app.seed import seed_reference_config
from app import semantic_similarity as semantic_similarity_module
from app.semantic_similarity import analyze_semantic_similarity, get_semantic_similarity_analyzer
from app.sentiment import get_sentiment_analyzer


def migrate(database_url: str) -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


def _ingest_single_review(session: Session, *, external_review_id: str) -> NormalizedReview:
    run_payload_ingestion(
        session,
        source_code="kingsbury_seed_dataset",
        connector_key="test_sentiment_runtime",
        payloads=[
            {
                "source_code": "kingsbury_seed_dataset",
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
                "severity": "medium",
                "department_code": "front_office",
            }
        ],
    )
    review = session.scalar(
        select(NormalizedReview).where(NormalizedReview.external_review_id == external_review_id)
    )
    assert review is not None
    assert review.analysis is not None
    return review


def _ingest_semantic_reviews(session: Session, *, connector_key: str) -> list[NormalizedReview]:
    run_payload_ingestion(
        session,
        source_code="kingsbury_seed_dataset",
        connector_key=connector_key,
        payloads=[
            {
                "source_code": "kingsbury_seed_dataset",
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
                "severity": "high",
                "department_code": "front_office",
            },
            {
                "source_code": "kingsbury_seed_dataset",
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
                "severity": "high",
                "department_code": "front_office",
            },
        ],
    )
    return list(session.scalars(select(NormalizedReview).order_by(NormalizedReview.id)))


def test_review_analysis_uses_deterministic_sentiment_fallback_with_metadata(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'sentiment-fallback.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    def unavailable_pipeline(**_):
        raise ImportError("transformers unavailable")

    monkeypatch.setattr(sentiment_module, "_load_transformer_pipeline", unavailable_pipeline)
    get_sentiment_analyzer.cache_clear()
    migrate(database_url)

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            seed_reference_config(session)
            review = _ingest_single_review(session, external_review_id="sentiment-fallback-001")

            assert review.analysis.model_name == "local-deterministic-review-analysis"
            assert review.analysis.model_version == "2026.07.demo-fallback"
            assert review.analysis.analysis_version == "analysis-v2"
            assert review.analysis.explanation_factors["model"]["sentiment_strategy"] == "deterministic_fallback"
            assert "transformer sentiment runtime was unavailable" in review.analysis.explanation_factors["model"]["fallback_note"]
            assert review.analysis.explanation_factors["model"]["sentiment_confidence"] == review.analysis.sentiment_confidence
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
            return [{"label": "POSITIVE", "score": 0.91}]

    monkeypatch.setattr(sentiment_module, "_load_transformer_pipeline", lambda **_: FakePipeline())
    get_sentiment_analyzer.cache_clear()
    migrate(database_url)

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            seed_reference_config(session)
            review = _ingest_single_review(session, external_review_id="sentiment-transformer-001")

            assert review.analysis.model_name == "local-transformer-sentiment-analysis"
            assert review.analysis.model_version == "commit-sha-123"
            assert review.analysis.analysis_version == "analysis-v2"
            assert review.analysis.sentiment_label == "positive"
            assert review.analysis.sentiment_score == 0.82
            assert review.analysis.sentiment_confidence == 0.91
            assert review.analysis.explanation_factors["model"]["sentiment_strategy"] == "local_transformer_pipeline"
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

        source_types = set(session.scalars(select(ReviewSource.source_type)))
        assert source_types == {
            "verified_review",
            "social_listening",
            "seed_dataset",
            "apify_dataset_import",
        }
        assert session.query(ReviewSource).count() == 6
        assert session.query(Department).count() == 6
        assert session.query(IssueCategory).count() == 11
        assert session.query(CategoryDepartmentMapping).count() == 12
        assert session.query(SeverityThreshold).count() == 11
        assert session.query(DemoRole).count() == 4

        reddit = session.get(ReviewSource, "reddit_social_listening")
        assert reddit is not None
        assert reddit.is_verified_channel is False
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
            select(NormalizedReview).where(NormalizedReview.external_review_id == "seed-kg-005")
        )
        assert analyzed_review is not None
        assert analyzed_review.analysis is not None
        assert analyzed_review.analysis.is_active is True
        assert analyzed_review.analysis.model_name == "local-deterministic-review-analysis"
        assert analyzed_review.analysis.model_version == "2026.07.demo-fallback"
        assert analyzed_review.analysis.analysis_version == "analysis-v2"
        assert analyzed_review.analysis.issue_category_code == "cleanliness"
        assert analyzed_review.analysis.department_code == "housekeeping"
        assert analyzed_review.analysis.severity_label in {"high", "critical"}
        assert analyzed_review.analysis.explanation_factors["severity"]["weights"]["rating"] > 0
        assert "fallback_note" in analyzed_review.analysis.explanation_factors["model"]
        primary_prediction = analyzed_review.analysis.issue_category_predictions[0]
        assert primary_prediction.category_code == "cleanliness"
        assert primary_prediction.confidence > 0
        assert primary_prediction.model_name == "keyword-baseline-issue-classifier"
        assert primary_prediction.model_version == "2026.07.demo-fallback"
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
                "source_code": "kingsbury_seed_dataset",
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
                "severity": "high",
                "department_code": "front_office",
            },
            {
                "source_code": "kingsbury_seed_dataset",
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
                "severity": "high",
                "department_code": "front_office",
            },
        ]

        first_run = run_payload_ingestion(
            session,
            source_code="kingsbury_seed_dataset",
            connector_key="test_content_dedupe",
            payloads=payloads,
        )
        second_run = run_payload_ingestion(
            session,
            source_code="kingsbury_seed_dataset",
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
            semantic_result = analyze_semantic_similarity(reviews, similarity_threshold=0.30)

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
            assert semantic_result.clusters[0].source_mix == {"kingsbury_seed_dataset": 2}
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
            semantic_result = analyze_semantic_similarity(reviews, similarity_threshold=0.30)

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
            source_code="kingsbury_seed_dataset",
            connector_key="test_recurring_issue_ticket",
            payloads=[
                {
                    "source_code": "kingsbury_seed_dataset",
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
                    "severity": "high",
                    "department_code": "front_office",
                },
                {
                    "source_code": "kingsbury_seed_dataset",
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
                    "severity": "high",
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
        category_code = initial_summary_response.json()["items"][0]["category_code"]
        category_response = client.post(
            f"/issues/categories/{category_code}/tickets",
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
    assert category_ticket["department_code"] in {"front_office", "guest_relations"}
    assert category_ticket["source_group_type"] == "category_recurrence"
    assert category_ticket["source_group_key"] == category_code
    assert category_ticket["source_category_code"] == category_code
    assert len(category_ticket["source_review_ids"]) == 2
    assert category_ticket["events"][0]["event_type"] == "created"

    assert initial_summary_response.status_code == 200
    assert summary_response.status_code == 200
    booking_summary = next(item for item in summary_response.json()["items"] if item["category_code"] == category_code)
    assert category_ticket["id"] in booking_summary["linked_ticket_ids"]

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


def test_verified_mock_connectors_are_independently_repeatable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'verified-connectors.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url)
    with Session(engine) as session:
        seed_reference_config(session)

        for connector_key in CONNECTORS:
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
        normalized_google = session.scalar(
            select(NormalizedReview).where(NormalizedReview.source_code == "google_business_profile")
        )
        assert normalized_google is not None
        assert normalized_google.normalized_payload["verified_review_source"] is True
        assert normalized_google.normalized_payload["mock_official_shaped_connector"] is True
        assert normalized_google.analysis is not None
        assert normalized_google.analysis.explanation_factors["department"]["mapping_source"] == "category_department_mappings.primary"


def test_reddit_social_listening_ingestion_is_repeatable_and_marked_separately(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'reddit-ingestion.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url)
    with Session(engine) as session:
        seed_reference_config(session)

        first_run = run_reddit_social_listening_ingestion(session)
        second_run = run_reddit_social_listening_ingestion(session)

        assert first_run.status == "completed"
        assert first_run.source_code == "reddit_social_listening"
        assert first_run.connector_key == "reddit_social_listening"
        assert first_run.records_created == 2
        assert second_run.records_created == 0
        assert second_run.records_skipped == 2

        reddit_records = list(
            session.scalars(
                select(NormalizedReview)
                .join(NormalizedReview.source)
                .where(ReviewSource.source_type == "social_listening")
            )
        )
        assert len(reddit_records) == 2
        assert {record.source_type for record in reddit_records} == {"social_listening"}
        assert {record.is_verified_channel for record in reddit_records} == {False}
        assert all(record.rating is None for record in reddit_records)
        assert all(record.analysis is not None for record in reddit_records)


def test_api_endpoints_expose_imports_and_social_listening_filters(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'api-config.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_reference_config(session)
        run_seed_ingestion(session)
        run_reddit_social_listening_ingestion(session)

    def override_get_session():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        config_response = client.get("/config")
        reviews_response = client.get("/reviews")
        reddit_reviews_response = client.get("/reviews", params={"source_type": "social_listening"})
        all_reviews_response = client.get("/reviews", params={"include_social_listening": "true"})
        cleanliness_reviews_response = client.get("/reviews", params={"issue_category_code": "cleanliness"})
        housekeeping_reviews_response = client.get("/reviews", params={"department_code": "housekeeping"})
        semantic_response = client.get("/analysis/semantic-clusters", params={"similarity_threshold": 0.30})
        runs_response = client.get("/ingestion/runs")
        reanalysis_response = client.post("/analysis/reanalyze")
        ingestion_response = client.post("/ingestion/seed")
        connector_response = client.post("/ingestion/connectors/google_business_profile")
        repeat_connector_response = client.post("/ingestion/connectors/google_business_profile")
        reddit_ingestion_response = client.post("/ingestion/reddit")
        source_status_response = client.get("/ingestion/source-status")
    finally:
        app.dependency_overrides.clear()

    assert config_response.status_code == 200
    payload = config_response.json()
    assert {source["source_type"] for source in payload["review_sources"]} == {
        "verified_review",
        "social_listening",
        "seed_dataset",
        "apify_dataset_import",
    }
    assert payload["review_sources"][0]["metadata"] is not None
    assert len(payload["departments"]) == 6
    assert len(payload["issue_categories"]) == 11
    assert len(payload["category_department_mappings"]) == 12
    assert len(payload["severity_thresholds"]) == 11
    assert len(payload["demo_roles"]) == 4

    assert reviews_response.status_code == 200
    default_reviews = reviews_response.json()["reviews"]
    assert len(default_reviews) == 6
    assert {review["source_type"] for review in default_reviews} == {"seed_dataset"}
    assert all(review["analysis"] is not None for review in default_reviews)
    assert all(review["analysis"]["severity_score"] >= 0 for review in default_reviews)
    assert all(review["analysis"]["model_version"] == "2026.07.demo-fallback" for review in default_reviews)
    assert all("severity" in review["analysis"]["explanation_factors"] for review in default_reviews)
    assert all(review["analysis"]["issue_category_predictions"] for review in default_reviews)
    assert all(
        {"category_code", "confidence", "model_name", "model_version", "analyzed_at"}
        <= set(review["analysis"]["issue_category_predictions"][0])
        for review in default_reviews
    )

    assert reddit_reviews_response.status_code == 200
    reddit_reviews = reddit_reviews_response.json()["reviews"]
    assert len(reddit_reviews) == 2
    assert {review["source_type"] for review in reddit_reviews} == {"social_listening"}
    assert all(review["is_verified_channel"] is False for review in reddit_reviews)

    assert all_reviews_response.status_code == 200
    assert len(all_reviews_response.json()["reviews"]) == 8
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
    assert len(runs_response.json()["runs"]) == 2
    assert reanalysis_response.status_code == 200
    assert reanalysis_response.json()["analyzed_count"] == 8
    assert ingestion_response.status_code == 200
    assert ingestion_response.json()["records_skipped"] == 6
    assert connector_response.status_code == 200
    assert connector_response.json()["records_created"] == 2
    assert repeat_connector_response.status_code == 200
    assert repeat_connector_response.json()["records_skipped"] == 2
    assert reddit_ingestion_response.status_code == 200
    assert reddit_ingestion_response.json()["records_skipped"] == 2
    assert source_status_response.status_code == 200
    source_statuses = source_status_response.json()["sources"]
    google_status = next(source for source in source_statuses if source["source_code"] == "google_business_profile")
    reddit_status = next(source for source in source_statuses if source["source_code"] == "reddit_social_listening")
    assert google_status["is_verified_channel"] is True
    assert google_status["latest_run"]["status"] == "completed"
    assert google_status["errors"] == []
    assert reddit_status["is_verified_channel"] is False
    assert reddit_status["source_type"] == "social_listening"


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
            source_code="kingsbury_seed_dataset",
            connector_key="test_search_redaction",
            payloads=[
                {
                    "source_code": "kingsbury_seed_dataset",
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
                    "severity": "high",
                    "department_code": "housekeeping",
                },
                {
                    "source_code": "kingsbury_seed_dataset",
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
                    "severity": "low",
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
        create_response = client.post(
            "/reviews/1/tickets",
            json={"department_code": "housekeeping", "priority": "medium", "notes": "Initial review."},
        )
        ticket_id = create_response.json()["id"]
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
        verify_response = client.patch(
            f"/tickets/{ticket_id}",
            json={"status": "verified", "notes": "Management verified."},
        )
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 201
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["status"] == "resolved"
    assert updated["priority"] == "urgent"
    assert updated["department_code"] == "guest_relations"
    assert updated["assignee_name"] == "Ops Manager"
    update_event_types = {event["event_type"] for event in updated["events"]}
    assert {"status_change", "priority_change", "department_change", "assignment_change", "due_date_change", "note_added"} <= update_event_types

    assert verify_response.status_code == 200
    verified = verify_response.json()
    assert verified["status"] == "verified"
    assert any(event["event_type"] == "status_change" and event["new_value"] == "verified" for event in verified["events"])


def test_apify_json_import_preserves_metadata_and_is_repeatable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'apify-json.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    export_path = tmp_path / "apify-export.json"
    export_path.write_text(
        """
        {
          "actorName": "apify/google-maps-reviews-scraper",
          "exportedAt": "2026-05-20T09:00:00+00:00",
          "platform": "google",
          "sourceUrl": "https://example.test/hotel",
          "items": [
            {
              "reviewId": "g-001",
              "reviewerName": "Ayesha F.",
              "publishedAt": "2026-05-19T12:30:00Z",
              "stars": "5",
              "reviewText": "Excellent stay and helpful staff."
            },
            {
              "reviewId": "g-002",
              "reviewerName": "Michael R.",
              "publishedAt": "2026-05-18T10:00:00+00:00",
              "stars": "2",
              "reviewText": "Check-in queue was very slow."
            },
            {
              "reviewId": "g-003",
              "stars": "4"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    engine = create_engine(database_url)
    with Session(engine) as session:
        seed_reference_config(session)

        first_run = run_apify_dataset_import(session, ApifyImportInput(file_path=str(export_path)))
        second_run = run_apify_dataset_import(session, ApifyImportInput(file_path=str(export_path)))

        assert first_run.status == "completed_with_errors"
        assert first_run.records_seen == 3
        assert first_run.records_created == 2
        assert first_run.error_count == 1
        assert "row 3: missing review text" in first_run.errors
        assert second_run.status == "completed_with_errors"
        assert second_run.records_created == 0
        assert second_run.records_skipped == 2
        assert session.query(RawReview).filter(RawReview.source_code == "apify_dataset_import").count() == 2
        assert session.query(NormalizedReview).filter(NormalizedReview.source_code == "apify_dataset_import").count() == 2
        assert session.query(ReviewAnalysis).count() == 2

        raw_review = session.scalar(select(RawReview).where(RawReview.external_review_id == "g-001"))
        assert raw_review is not None
        assert raw_review.raw_payload["record"]["reviewText"] == "Excellent stay and helpful staff."
        assert raw_review.raw_payload["dataset_metadata"]["actor_name"] == "apify/google-maps-reviews-scraper"

        normalized_review = session.scalar(
            select(NormalizedReview).where(NormalizedReview.external_review_id == "g-001")
        )
        assert normalized_review is not None
        metadata = normalized_review.normalized_payload["dataset_metadata"]
        assert normalized_review.source_code == "apify_dataset_import"
        assert normalized_review.source.is_verified_channel is False
        assert normalized_review.normalized_payload["source_kind"] == "dataset_import"
        assert metadata["actor_name"] == "apify/google-maps-reviews-scraper"
        assert metadata["export_date"] == "2026-05-20T09:00:00+00:00"
        assert metadata["platform"] == "google"
        assert metadata["source_url"] == "https://example.test/hotel"
        assert normalized_review.analysis is not None
        assert normalized_review.analysis.sentiment_label == "positive"
        assert normalized_review.analysis.department_code == "guest_relations"


def test_apify_import_reanalyzes_changed_reviews(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'apify-update.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    first_export_path = tmp_path / "apify-first.json"
    first_export_path.write_text(
        """
        [
          {
            "reviewId": "g-update-001",
            "reviewerName": "Ayesha F.",
            "publishedAt": "2026-05-19T12:30:00Z",
            "stars": "5",
            "reviewText": "Excellent stay and helpful staff."
          }
        ]
        """,
        encoding="utf-8",
    )
    changed_export_path = tmp_path / "apify-changed.json"
    changed_export_path.write_text(
        """
        [
          {
            "reviewId": "g-update-001",
            "reviewerName": "Ayesha F.",
            "publishedAt": "2026-05-19T12:30:00Z",
            "stars": "1",
            "reviewText": "Dirty bathroom floor and broken shower made the stay difficult."
          }
        ]
        """,
        encoding="utf-8",
    )

    engine = create_engine(database_url)
    with Session(engine) as session:
        seed_reference_config(session)

        first_run = run_apify_dataset_import(session, ApifyImportInput(file_path=str(first_export_path)))
        changed_run = run_apify_dataset_import(session, ApifyImportInput(file_path=str(changed_export_path)))

        assert first_run.records_created == 1
        assert changed_run.records_updated == 1
        assert session.query(ReviewAnalysis).count() == 1

        normalized_review = session.scalar(
            select(NormalizedReview).where(NormalizedReview.external_review_id == "g-update-001")
        )
        assert normalized_review is not None
        assert normalized_review.analysis is not None
        assert normalized_review.analysis.sentiment_label == "negative"
        assert normalized_review.analysis.issue_category_code == "cleanliness"
        assert normalized_review.analysis.department_code == "housekeeping"
        assert normalized_review.analysis.severity_label in {"high", "critical"}
        assert normalized_review.sentiment_label == normalized_review.analysis.sentiment_label
        assert normalized_review.department_code == normalized_review.analysis.department_code


def test_apify_csv_import_can_be_triggered_through_api(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'apify-api.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_reference_config(session)

    def override_get_session():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.post(
            "/ingestion/apify-dataset",
            json={
                "file_name": "apify-export.csv",
                "content": (
                    "reviewId,reviewerName,publishedAt,stars,reviewText,reviewUrl\n"
                    "csv-001,Nadeesha P.,2026-05-17T08:00:00Z,4,Great breakfast,https://example.test/reviews/csv-001\n"
                ),
                "actor_name": "apify/tripadvisor-reviews",
                "export_date": "2026-05-21T15:00:00+00:00",
                "platform": "tripadvisor",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["connector_key"] == "apify_dataset_import"
    assert payload["source_code"] == "apify_dataset_import"
    assert payload["records_seen"] == 1
    assert payload["records_created"] == 1
    assert payload["error_count"] == 0


def test_apify_import_reports_unsupported_input(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'apify-invalid.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    migrate(database_url)

    engine = create_engine(database_url)
    with Session(engine) as session:
        seed_reference_config(session)

        run = run_apify_dataset_import(
            session,
            ApifyImportInput(content="not an export", file_name="reviews.txt"),
        )

        assert run.status == "failed"
        assert run.error_count == 1
        assert run.errors == ["Unsupported Apify import input. Provide a .json or .csv export."]
