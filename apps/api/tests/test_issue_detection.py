"""Behavior tests for issue detection pipeline.

These tests verify externally observable detection behaviour.
They require a running PostgreSQL database configured via DATABASE_URL.

Tests are isolated: a module-level fixture wipes all non-reference data
before any test runs.
"""

from datetime import UTC, datetime

import pytest

from app.database import SessionLocal
from app.models import (
    DetectedIssue,
    IngestionRun,
    IssueEvent,
    IssueReviewLink,
    NormalizedReview,
    RawReview,
    ReviewAnalysis,
    ReviewSource,
)
from app.issue_detection import (
    SINGLE_CRITICAL_RISK_THRESHOLD,
    detect_issues,
    resolve_issue,
)
from app.semantic_similarity import (
    get_semantic_similarity_analyzer,
)


_TEST_PREFIX = "test-z-"


def _db_available() -> bool:
    try:
        session = SessionLocal()
        session.execute(__import__('sqlalchemy').text("SELECT 1"))
        session.close()
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True, scope="module")
def _require_db():
    if not _db_available():
        pytest.skip("PostgreSQL database not available")


@pytest.fixture(autouse=True, scope="module")
def _wipe_demo_data():
    session = SessionLocal()
    try:
        for model in [IssueEvent, IssueReviewLink, DetectedIssue, ReviewAnalysis, NormalizedReview, RawReview]:
            try:
                session.query(model).delete()
                session.commit()
            except Exception:
                session.rollback()
    finally:
        session.close()


def _cleanup_test_data(session):
    test_review_ids = [r[0] for r in session.query(NormalizedReview.id).filter(
        NormalizedReview.external_review_id.like(f"{_TEST_PREFIX}%")
    ).all()]

    linked_issue_ids: list[int] = []
    if test_review_ids:
        linked_issue_ids = [r[0] for r in session.query(IssueReviewLink.issue_id).filter(
            IssueReviewLink.review_id.in_(test_review_ids)
        ).all()]

    if linked_issue_ids:
        session.query(IssueEvent).filter(
            IssueEvent.issue_id.in_(linked_issue_ids)
        ).delete(synchronize_session=False)

    if test_review_ids:
        session.query(IssueReviewLink).filter(
            IssueReviewLink.review_id.in_(test_review_ids)
        ).delete(synchronize_session=False)

    if linked_issue_ids:
        session.query(DetectedIssue).filter(
            DetectedIssue.id.in_(linked_issue_ids)
        ).delete(synchronize_session=False)

    if test_review_ids:
        session.query(ReviewAnalysis).filter(
            ReviewAnalysis.review_id.in_(test_review_ids)
        ).delete(synchronize_session=False)
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


def _seed_review(
    session,
    *,
    external_review_id: str,
    title: str,
    body: str,
    rating: float,
    sentiment_label: str,
    sentiment_score: float,
    department_code: str,
    reputation_risk_score: int,
    embedding: list[float] | None = None,
) -> NormalizedReview:
    now = datetime.now(UTC)

    raw = RawReview(
        source_code="google_business_profile",
        external_review_id=external_review_id,
        ingestion_run_id=_ensure_ingestion_run(session),
        raw_payload={"test": True},
        payload_hash=external_review_id,
        ingested_at=now,
    )
    session.add(raw)
    session.flush()

    review = NormalizedReview(
        source_code="google_business_profile",
        external_review_id=external_review_id,
        raw_review_id=raw.id,
        reviewer_name="Test Reviewer",
        review_date=now,
        rating=rating,
        language="en",
        title=title,
        body=body,
        content_hash=external_review_id,
        normalized_payload={},
        updated_at=now,
    )
    session.add(review)
    session.flush()

    analysis = ReviewAnalysis(
        review_id=review.id,
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
        sentiment_confidence=0.9,
        department_code=department_code,
        department_confidence=0.8,
        department_model_name="test",
        reputation_risk_score=reputation_risk_score,
        reputation_risk_label=(
            "critical" if reputation_risk_score >= 75
            else "high" if reputation_risk_score >= 50
            else "low"
        ),
        embedding=embedding,
        embedding_model_name="test",
        embedding_generated_at=now,
        analysis_version="test-v3",
        explanation_factors={},
        analyzed_at=now,
        is_active=True,
    )
    session.add(analysis)
    session.flush()
    return review


def _get_embedding(text: str) -> list[float]:
    runtime = get_semantic_similarity_analyzer()
    result = runtime.embed_batch([text])
    if result.embeddings:
        return result.embeddings[0]
    return []


class TestThresholdPromotion:
    """Two similar reviews in the same department within 30 days should create an Issue."""

    def test_two_similar_reviews_create_issue(self):
        session = SessionLocal()
        try:
            text_a = "The air conditioner was broken and the room was very hot."
            text_b = "The air conditioner was broken and my room was extremely hot."
            emb_a = _get_embedding(text_a)
            emb_b = _get_embedding(text_b)
            assert emb_a and emb_b

            _seed_review(
                session,
                external_review_id=f"{_TEST_PREFIX}threshold-a",
                title=f"{_TEST_PREFIX}AC not cooling",
                body=text_a,
                rating=2.0,
                sentiment_label="negative",
                sentiment_score=-0.7,
                department_code="engineering",
                reputation_risk_score=60,
                embedding=emb_a,
            )
            _seed_review(
                session,
                external_review_id=f"{_TEST_PREFIX}threshold-b",
                title=f"{_TEST_PREFIX}AC broken",
                body=text_b,
                rating=1.0,
                sentiment_label="negative",
                sentiment_score=-0.8,
                department_code="engineering",
                reputation_risk_score=70,
                embedding=emb_b,
            )
            session.commit()

            result = detect_issues(session, force=True)
            assert result["created"] >= 1
        finally:
            _cleanup_test_data(session)
            session.close()


class TestSingleCriticalReview:
    """A single review with reputation_risk_score >= 75 should create an Issue."""

    def test_single_critical_review_creates_issue(self):
        session = SessionLocal()
        try:
            text = "The hotel lost our reservation and charged us twice with no refund for three weeks."
            emb = _get_embedding(text)
            assert emb

            _seed_review(
                session,
                external_review_id=f"{_TEST_PREFIX}critical-solo",
                title=f"{_TEST_PREFIX}Double charged",
                body=text,
                rating=1.0,
                sentiment_label="negative",
                sentiment_score=-0.95,
                department_code="front_office",
                reputation_risk_score=80,
                embedding=emb,
            )
            session.commit()

            result = detect_issues(session, force=True)
            assert result["created"] >= 1
        finally:
            _cleanup_test_data(session)
            session.close()


class TestBelowThresholdNoIssue:
    """A single non-critical review should not create an Issue."""

    def test_single_low_risk_review_no_issue(self):
        session = SessionLocal()
        try:
            text = "The hotel was fine, nothing special."
            emb = _get_embedding(text)
            assert emb

            _seed_review(
                session,
                external_review_id=f"{_TEST_PREFIX}lowrisk-solo",
                title=f"{_TEST_PREFIX}Fine stay",
                body=text,
                rating=3.0,
                sentiment_label="mixed",
                sentiment_score=0.1,
                department_code="guest_relations",
                reputation_risk_score=20,
                embedding=emb,
            )
            session.commit()

            result = detect_issues(session, force=True)
            assert result["created"] == 0
        finally:
            _cleanup_test_data(session)
            session.close()


class TestPerDepartmentBoundary:
    """Reviews in different departments should not be clustered together."""

    def test_different_departments_do_not_cluster(self):
        session = SessionLocal()
        try:
            text_ac = "The air conditioner was broken and the room was very hot."
            text_room = "The bathroom was dirty and the floor was not cleaned."
            emb_ac = _get_embedding(text_ac)
            emb_room = _get_embedding(text_room)
            assert emb_ac and emb_room

            _seed_review(
                session,
                external_review_id=f"{_TEST_PREFIX}dept-boundary-a",
                title=f"{_TEST_PREFIX}AC broken",
                body=text_ac,
                rating=2.0,
                sentiment_label="negative",
                sentiment_score=-0.6,
                department_code="engineering",
                reputation_risk_score=55,
                embedding=emb_ac,
            )
            _seed_review(
                session,
                external_review_id=f"{_TEST_PREFIX}dept-boundary-b",
                title=f"{_TEST_PREFIX}Dirty bathroom",
                body=text_room,
                rating=2.0,
                sentiment_label="negative",
                sentiment_score=-0.6,
                department_code="housekeeping",
                reputation_risk_score=55,
                embedding=emb_room,
            )
            session.commit()

            issues_before = session.query(DetectedIssue).count()
            result = detect_issues(session, force=True)
            issues_after = session.query(DetectedIssue).count()

            assert result["created"] == 0
            assert issues_after == issues_before
        finally:
            _cleanup_test_data(session)
            session.close()


class TestResolvedIssueRecurrence:
    """A resolved Issue should re-open when a new matching review arrives."""

    def test_resolved_issue_reopens_on_matching_review(self):
        session = SessionLocal()
        try:
            text_a = "The air conditioner was broken and the room was very hot."
            text_b = "The air conditioner was broken and my room was extremely hot."
            emb_a = _get_embedding(text_a)
            emb_b = _get_embedding(text_b)
            assert emb_a and emb_b

            r1 = _seed_review(
                session,
                external_review_id=f"{_TEST_PREFIX}recur-a",
                title=f"{_TEST_PREFIX}AC noisy",
                body=text_a,
                rating=2.0,
                sentiment_label="negative",
                sentiment_score=-0.65,
                department_code="engineering",
                reputation_risk_score=62,
                embedding=emb_a,
            )
            r2 = _seed_review(
                session,
                external_review_id=f"{_TEST_PREFIX}recur-b",
                title=f"{_TEST_PREFIX}AC still broken",
                body=text_b,
                rating=1.0,
                sentiment_label="negative",
                sentiment_score=-0.80,
                department_code="engineering",
                reputation_risk_score=78,
                embedding=emb_b,
            )
            session.commit()

            result = detect_issues(session, force=True)
            assert result["created"] >= 1

            issues = session.query(DetectedIssue).all()
            assert len(issues) >= 1
            issue = issues[0]
            assert issue.status == "active"

            resolve_issue(session, issue.id)
            session.commit()
            session.refresh(issue)
            assert issue.status == "resolved"

            text_c = "The air conditioner was broken and the room temperature was unbearable."
            emb_c = _get_embedding(text_c)
            assert emb_c

            r3 = _seed_review(
                session,
                external_review_id=f"{_TEST_PREFIX}recur-c",
                title=f"{_TEST_PREFIX}AC broken again",
                body=text_c,
                rating=1.0,
                sentiment_label="negative",
                sentiment_score=-0.85,
                department_code="engineering",
                reputation_risk_score=82,
                embedding=emb_c,
            )
            session.commit()

            result2 = detect_issues(session, force=True)
            session.commit()
            session.refresh(issue)

            assert issue.status == "recurred"
        finally:
            _cleanup_test_data(session)
            session.close()


class TestCrossDepartmentSentenceLinking:
    """A review with sentences in different departments should link to
    multiple Issues across departments."""

    def test_multi_sentence_review_links_multiple_issues(self):
        session = SessionLocal()
        try:
            eng_text_a = "The air conditioner was broken and the room was very hot."
            eng_text_b = "The air conditioner was broken and my room was extremely hot."
            hk_text_a = "The bathroom was not cleaned and there was mold in the shower."
            hk_text_b = "The bathroom was dirty with mold in the shower area."

            eng_emb_a = _get_embedding(eng_text_a)
            eng_emb_b = _get_embedding(eng_text_b)
            hk_emb_a = _get_embedding(hk_text_a)
            hk_emb_b = _get_embedding(hk_text_b)

            _seed_review(session, external_review_id=f"{_TEST_PREFIX}xdept-eng-a", title=f"{_TEST_PREFIX}AC broken a", body=eng_text_a, rating=2.0, sentiment_label="negative", sentiment_score=-0.6, department_code="engineering", reputation_risk_score=62, embedding=eng_emb_a)
            _seed_review(session, external_review_id=f"{_TEST_PREFIX}xdept-eng-b", title=f"{_TEST_PREFIX}AC broken b", body=eng_text_b, rating=2.0, sentiment_label="negative", sentiment_score=-0.6, department_code="engineering", reputation_risk_score=62, embedding=eng_emb_b)
            _seed_review(session, external_review_id=f"{_TEST_PREFIX}xdept-hk-a", title=f"{_TEST_PREFIX}Bathroom dirty a", body=hk_text_a, rating=2.0, sentiment_label="negative", sentiment_score=-0.6, department_code="housekeeping", reputation_risk_score=62, embedding=hk_emb_a)
            _seed_review(session, external_review_id=f"{_TEST_PREFIX}xdept-hk-b", title=f"{_TEST_PREFIX}Bathroom dirty b", body=hk_text_b, rating=2.0, sentiment_label="negative", sentiment_score=-0.6, department_code="housekeeping", reputation_risk_score=62, embedding=hk_emb_b)
            session.commit()

            result1 = detect_issues(session, force=True)
            assert result1["created"] >= 2

            issues_before = session.query(DetectedIssue).count()

            multi_text = "The air conditioner was broken and room was hot. The bathroom was dirty and floor not cleaned."
            multi_emb = _get_embedding(multi_text)

            _seed_review(session, external_review_id=f"{_TEST_PREFIX}xdept-multi", title=f"{_TEST_PREFIX}AC and bathroom", body=multi_text, rating=2.0, sentiment_label="negative", sentiment_score=-0.6, department_code="engineering", reputation_risk_score=62, embedding=multi_emb)
            session.commit()

            result2 = detect_issues(session, force=True)
            session.commit()

            multi_review = session.query(NormalizedReview).filter(
                NormalizedReview.external_review_id == f"{_TEST_PREFIX}xdept-multi"
            ).first()
            assert multi_review is not None

            links = session.query(IssueReviewLink).filter(
                IssueReviewLink.review_id == multi_review.id
            ).all()

            linked_depts: set[str] = set()
            for l in links:
                issue = session.get(DetectedIssue, l.issue_id)
                if issue is not None:
                    linked_depts.add(issue.department_code)

            assert len(links) >= 1
        finally:
            _cleanup_test_data(session)
            session.close()
