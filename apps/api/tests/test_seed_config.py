from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.apify_importer import ApifyImportInput, run_apify_dataset_import
from app.connectors.registry import CONNECTORS
from app.database import get_session
from app.ingestion import normalized_content_hash, run_mock_connector_by_key, run_payload_ingestion, run_seed_ingestion
from app.main import app
from app.models import (
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
)
from app.reddit_import import run_reddit_social_listening_ingestion
from app.seed import seed_reference_config


def migrate(database_url: str) -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


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
        assert analyzed_review.analysis.analysis_version == "analysis-v1"
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
