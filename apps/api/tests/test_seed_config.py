from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_session
from app.ingestion import run_seed_ingestion
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
