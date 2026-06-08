"""Behavior tests for the LLM-driven issue detection pipeline.

These run against a PostgreSQL test database and use the deterministic offline ``stub`` LLM
provider (no network), so they assert the pipeline's structural behaviour rather than model
quality:

* synonymous complaints consolidate into ONE issue,
* a materially distinct incident (pest/hygiene) stays its own issue,
* a single supporting review becomes an ``emerging`` candidate (not ``active``),
* manual state (resolved) survives a rebuild via the stable cluster_key.

Detection is a full rebuild, so tests query the issues linked to their own seeded reviews
rather than global counts.
"""

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from app.database import SessionLocal
from app.models import (
    DetectedIssue,
    IngestionRun,
    IssueEvent,
    IssueReviewLink,
    NormalizedReview,
    RawReview,
    ReviewAnalysis,
)
from app.issue_detection import detect_issues, resolve_issue
from app import llm_client


_TEST_PREFIX = "test-z-"


@pytest.fixture(autouse=True)
def _use_stub_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    llm_client.reset_llm_client_cache()
    yield
    llm_client.reset_llm_client_cache()


def _db_available() -> bool:
    try:
        session = SessionLocal()
        session.execute(sa.text("SELECT 1"))
        session.close()
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True, scope="module")
def _require_db():
    if not _db_available():
        pytest.skip("PostgreSQL database not available")


@pytest.fixture(autouse=True)
def _cleanup():
    session = SessionLocal()
    try:
        _cleanup_test_data(session)
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        _cleanup_test_data(session)
    finally:
        session.close()


def _cleanup_test_data(session):
    test_review_ids = [r[0] for r in session.query(NormalizedReview.id).filter(
        NormalizedReview.external_review_id.like(f"{_TEST_PREFIX}%")
    ).all()]

    issue_ids: list[int] = []
    if test_review_ids:
        issue_ids = [r[0] for r in session.query(IssueReviewLink.issue_id).filter(
            IssueReviewLink.review_id.in_(test_review_ids)
        ).all()]

    if issue_ids:
        session.query(IssueEvent).filter(IssueEvent.issue_id.in_(issue_ids)).delete(synchronize_session=False)
        session.query(IssueReviewLink).filter(IssueReviewLink.issue_id.in_(issue_ids)).delete(synchronize_session=False)
        session.query(DetectedIssue).filter(DetectedIssue.id.in_(issue_ids)).delete(synchronize_session=False)
    if test_review_ids:
        session.query(ReviewAnalysis).filter(ReviewAnalysis.review_id.in_(test_review_ids)).delete(synchronize_session=False)
        session.query(NormalizedReview).filter(
            NormalizedReview.external_review_id.like(f"{_TEST_PREFIX}%")
        ).delete(synchronize_session=False)
        session.query(RawReview).filter(
            RawReview.external_review_id.like(f"{_TEST_PREFIX}%")
        ).delete(synchronize_session=False)
    session.commit()


def _ensure_ingestion_run(session) -> int:
    run = session.query(IngestionRun).filter(
        IngestionRun.source_code == "google_business_profile"
    ).first()
    if run is None:
        run = IngestionRun(
            connector_key="google_business_profile",
            source_code="google_business_profile",
            status="completed",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            records_seen=0,
        )
        session.add(run)
        session.flush()
    return run.id


def _seed_review(session, *, suffix: str, body: str, risk: int = 60) -> NormalizedReview:
    now = datetime.now(UTC)
    external = f"{_TEST_PREFIX}{suffix}"
    raw = RawReview(
        source_code="google_business_profile",
        external_review_id=external,
        ingestion_run_id=_ensure_ingestion_run(session),
        raw_payload={"test": True},
        payload_hash=external,
        ingested_at=now,
    )
    session.add(raw)
    session.flush()
    review = NormalizedReview(
        source_code="google_business_profile",
        external_review_id=external,
        raw_review_id=raw.id,
        reviewer_name="Test Reviewer",
        review_date=now,
        rating=2.0,
        language="en",
        title=None,
        body=body,
        content_hash=external,
        normalized_payload={},
        updated_at=now,
    )
    session.add(review)
    session.flush()
    analysis = ReviewAnalysis(
        review_id=review.id,
        sentiment_label="negative",
        sentiment_score=-0.7,
        sentiment_confidence=0.9,
        department_code="guest_relations",
        department_confidence=0.8,
        department_model_name="test",
        reputation_risk_score=risk,
        reputation_risk_label="high" if risk >= 50 else "low",
        embedding=None,
        embedding_model_name=None,
        embedding_generated_at=now,
        analysis_version="test-v3",
        explanation_factors={},
        analyzed_at=now,
        is_active=True,
    )
    session.add(analysis)
    session.flush()
    return review


def _issues_for(session, review_ids: list[int]) -> list[DetectedIssue]:
    issue_ids = {
        r[0]
        for r in session.query(IssueReviewLink.issue_id).filter(
            IssueReviewLink.review_id.in_(review_ids)
        ).all()
    }
    return [session.get(DetectedIssue, i) for i in issue_ids]


class TestConsolidation:
    def test_synonymous_complaints_form_one_issue(self):
        session = SessionLocal()
        try:
            ids = [
                _seed_review(session, suffix="ac-1", body="The air conditioning in room 412 did not cool, it stayed hot all night.").id,
                _seed_review(session, suffix="ac-2", body="AC in room 905 never got cold, the room would not cool down.").id,
                _seed_review(session, suffix="ac-3", body="Air conditioning broken in room 220, it was too hot and would not cool.").id,
            ]
            session.commit()

            detect_issues(session, force=True)

            issues = _issues_for(session, ids)
            assert len(issues) == 1
            issue = issues[0]
            assert issue.department_code == "engineering"
            assert issue.status == "active"
            assert issue.recurrence_count == 3
            assert issue.description  # description was generated
        finally:
            _cleanup_test_data(session)
            session.close()


class TestSpecificIncidentStaysSeparate:
    def test_pest_incident_not_folded_into_other_issue(self):
        session = SessionLocal()
        try:
            ac_ids = [
                _seed_review(session, suffix="s-ac-1", body="The air conditioning in room 301 did not cool the room at all.").id,
                _seed_review(session, suffix="s-ac-2", body="AC would not cool in room 808, far too hot to sleep.").id,
            ]
            pest_ids = [
                _seed_review(session, suffix="s-bug-1", body="There was a cockroach in the pancakes at breakfast, disgusting.").id,
                _seed_review(session, suffix="s-bug-2", body="Found an insect crawling in the food at the buffet.").id,
            ]
            session.commit()

            detect_issues(session, force=True)

            ac_issues = _issues_for(session, ac_ids)
            pest_issues = _issues_for(session, pest_ids)
            assert len(ac_issues) == 1
            assert len(pest_issues) == 1
            assert ac_issues[0].id != pest_issues[0].id
            assert ac_issues[0].department_code == "engineering"
            assert pest_issues[0].department_code == "housekeeping"
        finally:
            _cleanup_test_data(session)
            session.close()


class TestEmergingSingleton:
    def test_single_review_is_emerging_not_active(self):
        session = SessionLocal()
        try:
            rid = _seed_review(session, suffix="solo-ac", body="The air conditioning in room 117 did not cool at all.").id
            session.commit()

            result = detect_issues(session, force=True)

            issues = _issues_for(session, [rid])
            assert len(issues) == 1
            assert issues[0].status == "emerging"
            assert result.get("emerging", 0) >= 1
        finally:
            _cleanup_test_data(session)
            session.close()


class TestResolvedStatePreserved:
    def test_resolved_issue_stays_resolved_after_rebuild(self):
        session = SessionLocal()
        try:
            ids = [
                _seed_review(session, suffix="r-ac-1", body="The air conditioning in room 410 did not cool, stayed hot.").id,
                _seed_review(session, suffix="r-ac-2", body="AC in room 511 would not cool down at all.").id,
            ]
            session.commit()

            detect_issues(session, force=True)
            issue = _issues_for(session, ids)[0]
            assert issue.status == "active"

            resolve_issue(session, issue.id)
            session.commit()

            detect_issues(session, force=True)
            rebuilt = _issues_for(session, ids)[0]
            assert rebuilt.status == "resolved"
        finally:
            _cleanup_test_data(session)
            session.close()
