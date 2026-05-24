from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.apify_importer import ApifyImportInput, run_apify_dataset_import
from app.database import get_session
from app.connectors.registry import CONNECTORS
from app.ingestion import run_mock_connector_by_key, run_seed_ingestion
from app.main import app
from app.models import (
    CategoryDepartmentMapping,
    DemoRole,
    Department,
    IngestionRun,
    IssueCategory,
    NormalizedReview,
    RawReview,
    ReviewSource,
    SeverityThreshold,
)
from app.seed import seed_reference_config


def test_migrations_and_seed_are_repeatable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'config.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

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

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

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
        assert session.query(IngestionRun).count() == 2
        assert session.query(RawReview).count() == 6
        assert session.query(NormalizedReview).count() == 6


def test_verified_mock_connectors_are_independently_repeatable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'verified-connectors.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

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
        raw_google = session.scalar(select(RawReview).where(RawReview.source_code == "google_business_profile"))
        assert raw_google is not None
        assert "reviewId" in raw_google.raw_payload
        normalized_google = session.scalar(
            select(NormalizedReview).where(NormalizedReview.source_code == "google_business_profile")
        )
        assert normalized_google is not None
        assert normalized_google.normalized_payload["verified_review_source"] is True
        assert normalized_google.normalized_payload["mock_official_shaped_connector"] is True


def test_config_endpoint_returns_seeded_reference_data(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'api-config.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

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
        config_response = client.get("/config")
        reviews_response = client.get("/reviews")
        runs_response = client.get("/ingestion/runs")
        ingestion_response = client.post("/ingestion/seed")
        connector_response = client.post("/ingestion/connectors/google_business_profile")
        repeat_connector_response = client.post("/ingestion/connectors/google_business_profile")
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
    assert len(reviews_response.json()["reviews"]) == 6
    assert runs_response.status_code == 200
    assert len(runs_response.json()["runs"]) == 1
    assert ingestion_response.status_code == 200
    assert ingestion_response.json()["records_skipped"] == 6
    assert connector_response.status_code == 200
    assert connector_response.json()["records_created"] == 2
    assert repeat_connector_response.status_code == 200
    assert repeat_connector_response.json()["records_skipped"] == 2
    assert source_status_response.status_code == 200
    source_statuses = source_status_response.json()["sources"]
    google_status = next(source for source in source_statuses if source["source_code"] == "google_business_profile")
    assert google_status["is_verified_channel"] is True
    assert google_status["latest_run"]["status"] == "completed"
    assert google_status["errors"] == []


def test_apify_json_import_preserves_metadata_and_is_repeatable(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'apify-json.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

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


def test_apify_csv_import_can_be_triggered_through_api(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'apify-api.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

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

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

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
