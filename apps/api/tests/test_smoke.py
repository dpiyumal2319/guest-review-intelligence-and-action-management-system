from app.database import SessionLocal, get_session
from app.main import app
from app.models import (
    Base,
    DemoRole,
    Department,
    DetectedIssue,
    IngestionRun,
    IssueEvent,
    IssueReviewLink,
    NormalizedReview,
    RawReview,
    ReviewAnalysis,
    ReviewSource,
)
from app.schemas import (
    DetectedIssueCompactResponse,
    DetectedIssueDetailResponse,
    IssueEmergingResponse,
    IssuesResponse,
    OverviewKpiResponse,
    ReviewResponse,
    ReviewsResponse,
)
from app.sentiment import ANALYSIS_VERSION
from app.ml.department_classifier import DEPARTMENT_LABELS, DEPARTMENT_LABEL_TO_CODE


def test_models_import():
    assert len(DEPARTMENT_LABELS) == 6
    assert "engineering" in DEPARTMENT_LABELS[3]


def test_schemas_import():
    assert IssuesResponse is not None
    assert ReviewsResponse is not None
    assert OverviewKpiResponse is not None
    assert DetectedIssueDetailResponse is not None
    assert DetectedIssueCompactResponse is not None
    assert IssueEmergingResponse is not None
    assert ReviewResponse is not None


def test_analysis_version():
    assert ANALYSIS_VERSION == "analysis-v3"


def test_app_has_routes():
    assert len(app.routes) > 10


def test_department_labels():
    expected_codes = {"housekeeping", "front_office", "food_beverage", "engineering", "management", "guest_relations"}
    assert set(DEPARTMENT_LABEL_TO_CODE.values()) == expected_codes
    assert len(DEPARTMENT_LABELS) == 6
