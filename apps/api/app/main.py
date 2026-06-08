from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.analysis import reanalyze_reviews
from app.analysis_runtime import AnalysisRuntimeUnavailableError
from app.connectors.registry import CONNECTORS
from app.database import get_session
from app.ingestion import run_mock_connector_by_key
from app.issue_detection import detect_issues, list_emerging_candidates, resolve_issue
from app.models import (
    DemoRole,
    Department,
    DetectedIssue,
    IngestionRun,
    IssueEvent,
    IssueReviewLink,
    NormalizedReview,
    ReviewAnalysis,
    ReviewSource,
)
from app.schemas import (
    ConnectorImportRequest,
    DashboardActionMetricResponse,
    DashboardAgingRiskResponse,
    DashboardDrillThroughResponse,
    DashboardIssueItemResponse,
    DashboardIssueMetricResponse,
    DashboardOwnerPressureItemResponse,
    DashboardPlatformRiskItemResponse,
    DemoRoleResponse,
    DepartmentResponse,
    DetectedIssueCompactResponse,
    DetectedIssueDetailResponse,
    HealthResponse,
    IngestionRunResponse,
    IngestionRunsResponse,
    IngestionSourceStatusesResponse,
    IssueDetectResponse,
    IssueEmergingResponse,
    IssueUpdateRequest,
    IssuesResponse,
    OverviewActionAnalyticsResponse,
    OverviewKpiResponse,
    OverviewDepartmentCountResponse,
    ReanalysisResponse,
    ReferenceConfigResponse,
    ReviewResponse,
    ReviewsResponse,
    ReviewSourceResponse,
    SemanticAnalysisResponse,
)
from app.semantic_similarity import (
    DEFAULT_MIN_CLUSTER_SIZE,
    DEFAULT_SIMILARITY_THRESHOLD,
    analyze_semantic_similarity,
)
from app.seed_data import REVIEW_SOURCES


MVP_REVIEW_SOURCE_CODES = tuple(source["code"] for source in REVIEW_SOURCES)


app = FastAPI(
    title="Guest Review Intelligence API",
    summary="REST API for the hotel review intelligence prototype.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_VALID_SENTIMENT_LABELS = {"positive", "mixed", "negative"}
_VALID_REPUTATION_RISK_LABELS = {"low", "medium", "high", "critical"}
_VALID_ISSUE_STATUSES = {"active", "resolved", "recurred"}
_VALID_ISSUE_PRIORITIES = {"low", "medium", "high", "urgent"}


@app.get("/health", tags=["system"], response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="api")


@app.get("/config", tags=["configuration"], response_model=ReferenceConfigResponse)
async def reference_config(session: Session = Depends(get_session)) -> ReferenceConfigResponse:
    return ReferenceConfigResponse(
        review_sources=list(
            session.scalars(
                select(ReviewSource)
                .where(ReviewSource.code.in_(MVP_REVIEW_SOURCE_CODES))
                .order_by(ReviewSource.code)
            )
        ),
        departments=list(session.scalars(select(Department).order_by(Department.sort_order))),
        demo_roles=list(session.scalars(select(DemoRole).order_by(DemoRole.code))),
    )


@app.post("/ingestion/connectors/{connector_key}", tags=["ingestion"], response_model=IngestionRunResponse)
async def import_verified_connector(
    connector_key: str,
    request: ConnectorImportRequest | None = None,
    session: Session = Depends(get_session),
) -> IngestionRun:
    if connector_key not in CONNECTORS:
        raise HTTPException(status_code=404, detail=f"Unknown connector '{connector_key}'")
    run = run_mock_connector_by_key(session, connector_key, fixture_path=request.fixture_path if request else None)
    if run.status == "failed":
        raise HTTPException(status_code=503, detail=run.errors[0] if run.errors else "Analysis failed during connector import.")
    return run


@app.get("/ingestion/runs", tags=["ingestion"], response_model=IngestionRunsResponse)
async def ingestion_runs(session: Session = Depends(get_session)) -> IngestionRunsResponse:
    runs = list(session.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(10)))
    return IngestionRunsResponse(runs=runs)


@app.get("/ingestion/source-status", tags=["ingestion"], response_model=IngestionSourceStatusesResponse)
async def ingestion_source_status(session: Session = Depends(get_session)) -> IngestionSourceStatusesResponse:
    sources = list(
        session.scalars(
            select(ReviewSource)
            .where(ReviewSource.code.in_(MVP_REVIEW_SOURCE_CODES))
            .order_by(ReviewSource.code)
        )
    )
    statuses = []
    for source in sources:
        latest_run = None
        if source.connector_key:
            latest_run = session.scalar(
                select(IngestionRun)
                .where(IngestionRun.source_code == source.code)
                .order_by(IngestionRun.started_at.desc())
                .limit(1)
            )
        statuses.append(
            {
                "source_code": source.code,
                "source_name": source.name,
                "connector_key": source.connector_key,
                "is_verified_channel": source.is_verified_channel,
                "latest_run": latest_run,
                "errors": latest_run.errors if latest_run is not None else [],
            }
        )
    return IngestionSourceStatusesResponse(sources=statuses)


@app.get("/reviews", tags=["reviews"], response_model=ReviewsResponse)
async def reviews(
    source_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    reputation_risk: str | None = Query(default=None),
    risk_group: str | None = Query(default=None),
    has_issues: bool | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1),
    order_by: str = Query(default="review_date"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> ReviewsResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if reputation_risk is not None and reputation_risk not in _VALID_REPUTATION_RISK_LABELS:
        raise HTTPException(status_code=422, detail=f"reputation_risk must be one of {sorted(_VALID_REPUTATION_RISK_LABELS)}")
    if risk_group is not None and risk_group not in {"high_or_critical"}:
        raise HTTPException(status_code=422, detail=f"risk_group must be 'high_or_critical'")
    if order_by not in {"review_date", "operational_priority"}:
        raise HTTPException(status_code=422, detail="order_by must be one of ['operational_priority', 'review_date']")

    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(
            selectinload(NormalizedReview.source),
            selectinload(NormalizedReview.analysis),
            selectinload(NormalizedReview.issue_links),
        )
    )
    query = query.where(NormalizedReview.source_code.in_(MVP_REVIEW_SOURCE_CODES))
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)
    if department_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(ReviewAnalysis.department_code == department_code)
        )
    if sentiment_label is not None:
        query = query.where(
            NormalizedReview.analysis.has(ReviewAnalysis.sentiment_label == sentiment_label)
        )
    if reputation_risk is not None:
        query = query.where(
            NormalizedReview.analysis.has(ReviewAnalysis.reputation_risk_label == reputation_risk)
        )
    if risk_group == "high_or_critical":
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.reputation_risk_label.in_(["high", "critical"])
            )
        )
    if has_issues is True:
        query = query.where(NormalizedReview.issue_links.any())
    elif has_issues is False:
        query = query.where(~NormalizedReview.issue_links.any())
    if date_from is not None:
        query = query.where(NormalizedReview.review_date >= date_from)
    if date_to is not None:
        query = query.where(NormalizedReview.review_date <= date_to)
    if search is not None:
        query = query.where(
            or_(
                NormalizedReview.body.ilike(f"%{search}%"),
                NormalizedReview.title.ilike(f"%{search}%"),
                NormalizedReview.external_review_id.ilike(f"%{search}%"),
                NormalizedReview.reviewer_name.ilike(f"%{search}%"),
            )
        )

    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0

    order_clauses = []
    if order_by == "operational_priority":
        order_clauses = [
            case(
                (ReviewAnalysis.reputation_risk_label == "critical", 4),
                (ReviewAnalysis.reputation_risk_label == "high", 3),
                (ReviewAnalysis.reputation_risk_label == "medium", 2),
                else_=1,
            ).desc(),
            NormalizedReview.review_date.desc(),
            NormalizedReview.id.desc(),
        ]
    else:
        order_clauses = [
            NormalizedReview.review_date.desc(),
            NormalizedReview.id.desc(),
        ]

    imported_reviews = list(
        session.scalars(
            query.order_by(*order_clauses)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )

    review_payloads = []
    for review in imported_reviews:
        payload = ReviewResponse.model_validate(review).model_dump()
        if payload["analysis"] is not None:
            payload["analysis"].pop("model", None)
            payload["analysis"].pop("explanation_factors", None)
        review_payloads.append(payload)

    total_pages = (total + per_page - 1) // per_page if total else 0
    return ReviewsResponse(
        reviews=review_payloads,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@app.get("/analysis/semantic-clusters", tags=["analysis"], response_model=SemanticAnalysisResponse)
async def semantic_clusters(
    source_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    similarity_threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    min_cluster_size: int = Query(default=DEFAULT_MIN_CLUSTER_SIZE, ge=2, le=20),
    session: Session = Depends(get_session),
) -> SemanticAnalysisResponse:
    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(
            selectinload(NormalizedReview.source),
            selectinload(NormalizedReview.analysis),
        )
    )
    query = query.where(NormalizedReview.source_code.in_(MVP_REVIEW_SOURCE_CODES))
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)
    if department_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(ReviewAnalysis.department_code == department_code)
        )

    imported_reviews = list(session.scalars(query.order_by(NormalizedReview.review_date.desc(), NormalizedReview.id)))
    semantic_result = analyze_semantic_similarity(
        imported_reviews,
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
    )
    return SemanticAnalysisResponse.model_validate(asdict(semantic_result))


@app.post("/analysis/reanalyze", tags=["analysis"], response_model=ReanalysisResponse)
async def reanalyze_imported_reviews(
    source_code: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ReanalysisResponse:
    try:
        analyzed_count = reanalyze_reviews(session, source_code=source_code)
    except AnalysisRuntimeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ReanalysisResponse(analyzed_count=analyzed_count)


@app.get("/issues", tags=["issues"], response_model=IssuesResponse)
async def list_issues(
    status: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    min_risk: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> IssuesResponse:
    if status is not None and status not in _VALID_ISSUE_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(_VALID_ISSUE_STATUSES)}")
    if priority is not None and priority not in _VALID_ISSUE_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"priority must be one of {sorted(_VALID_ISSUE_PRIORITIES)}")

    query = select(DetectedIssue)
    if status is not None:
        query = query.where(DetectedIssue.status == status)
    else:
        # Emerging issues are low-confidence candidates surfaced via /issues/emerging only.
        query = query.where(DetectedIssue.status != "emerging")
    if department_code is not None:
        query = query.where(DetectedIssue.department_code == department_code)
    if priority is not None:
        query = query.where(DetectedIssue.priority == priority)
    if assignee is not None:
        query = query.where(DetectedIssue.assignee_name == assignee)
    if min_risk is not None:
        query = query.where(DetectedIssue.reputation_risk_score >= min_risk)

    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    issues = list(
        session.scalars(
            query.order_by(
                DetectedIssue.status.asc(),
                DetectedIssue.reputation_risk_score.desc(),
                DetectedIssue.last_seen_at.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    total_pages = (total + per_page - 1) // per_page if total else 0
    return IssuesResponse(
        issues=issues,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@app.get("/issues/emerging", tags=["issues"], response_model=list[IssueEmergingResponse])
async def emerging_issues(
    session: Session = Depends(get_session),
) -> list[IssueEmergingResponse]:
    candidates = list_emerging_candidates(session)
    return candidates


@app.post("/issues/detect", tags=["issues"], response_model=IssueDetectResponse)
async def detect_issues_endpoint(
    force: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> IssueDetectResponse:
    from app.llm_client import get_llm_client

    client = get_llm_client()
    if not client.is_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "LLM provider is not configured. Set GEMINI_API_KEY (LLM_PROVIDER=gemini) "
                "or LLM_PROVIDER=stub for an offline run."
            ),
        )

    result = detect_issues(session, force=force)

    issues = list(
        session.scalars(
            select(DetectedIssue).order_by(DetectedIssue.created_at.desc()).limit(result["created"] or 10)
        )
    )

    return IssueDetectResponse(
        created=result["created"],
        updated=result["updated"],
        linked=result["linked"],
        merged=result.get("merged", 0),
        issues=issues,
    )


@app.get("/issues/{issue_id}", tags=["issues"], response_model=DetectedIssueDetailResponse)
async def get_issue(
    issue_id: int,
    session: Session = Depends(get_session),
) -> DetectedIssue:
    issue = session.scalar(
        select(DetectedIssue)
        .where(DetectedIssue.id == issue_id)
        .options(
            selectinload(DetectedIssue.review_links),
            selectinload(DetectedIssue.events),
        )
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@app.patch("/issues/{issue_id}", tags=["issues"], response_model=DetectedIssueCompactResponse)
async def update_issue(
    issue_id: int,
    body: IssueUpdateRequest,
    session: Session = Depends(get_session),
) -> DetectedIssue:
    issue = session.get(DetectedIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    now = datetime.now(timezone.utc)

    if body.priority is not None:
        if body.priority not in _VALID_ISSUE_PRIORITIES:
            raise HTTPException(status_code=422, detail=f"priority must be one of {sorted(_VALID_ISSUE_PRIORITIES)}")
        if body.priority != issue.priority:
            session.add(
                IssueEvent(
                    issue_id=issue.id,
                    event_type="priority_changed",
                    actor="system",
                    old_value=issue.priority,
                    new_value=body.priority,
                    note="Priority updated via API",
                    created_at=now,
                )
            )
            issue.priority = body.priority

    if body.assignee_name is not None and body.assignee_name != issue.assignee_name:
        session.add(
            IssueEvent(
                issue_id=issue.id,
                event_type="assignee_changed",
                actor="system",
                old_value=issue.assignee_name,
                new_value=body.assignee_name,
                note=f"Assignee changed to {body.assignee_name}",
                created_at=now,
            )
        )
        issue.assignee_name = body.assignee_name

    issue.updated_at = now
    session.commit()
    session.refresh(issue)
    return issue


@app.patch("/issues/{issue_id}/resolve", tags=["issues"], response_model=DetectedIssueCompactResponse)
async def resolve_issue_endpoint(
    issue_id: int,
    session: Session = Depends(get_session),
) -> DetectedIssue:
    issue = resolve_issue(session, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@app.get("/overview/kpis", tags=["overview"], response_model=OverviewKpiResponse)
async def overview_kpis(
    source_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    reputation_risk: str | None = Query(default=None),
    risk_group: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> OverviewKpiResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if reputation_risk is not None and reputation_risk not in _VALID_REPUTATION_RISK_LABELS:
        raise HTTPException(status_code=422, detail=f"reputation_risk must be one of {sorted(_VALID_REPUTATION_RISK_LABELS)}")
    if risk_group is not None and risk_group not in {"high_or_critical"}:
        raise HTTPException(status_code=422, detail=f"risk_group must be 'high_or_critical'")

    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(selectinload(NormalizedReview.analysis))
    )
    query = query.where(NormalizedReview.source_code.in_(MVP_REVIEW_SOURCE_CODES))
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)
    if department_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(ReviewAnalysis.department_code == department_code)
        )
    if sentiment_label is not None:
        query = query.where(
            NormalizedReview.analysis.has(ReviewAnalysis.sentiment_label == sentiment_label)
        )
    if reputation_risk is not None:
        query = query.where(
            NormalizedReview.analysis.has(ReviewAnalysis.reputation_risk_label == reputation_risk)
        )
    if risk_group == "high_or_critical":
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.reputation_risk_label.in_(["high", "critical"])
            )
        )
    if date_from is not None:
        query = query.where(NormalizedReview.review_date >= date_from)
    if date_to is not None:
        query = query.where(NormalizedReview.review_date <= date_to)

    matched_reviews = list(session.scalars(query))
    total = len(matched_reviews)

    sentiment_mix = {label: 0 for label in _VALID_SENTIMENT_LABELS}
    reputation_risk_mix = {label: 0 for label in _VALID_REPUTATION_RISK_LABELS}
    department_counts: dict[str, int] = {}
    rating_total = 0.0
    rating_count = 0
    reputation_risk_score_total = 0
    reputation_risk_score_count = 0

    for review in matched_reviews:
        if review.analysis is not None:
            if review.analysis.sentiment_label in sentiment_mix:
                sentiment_mix[review.analysis.sentiment_label] += 1
            if review.analysis.reputation_risk_label in reputation_risk_mix:
                reputation_risk_mix[review.analysis.reputation_risk_label] += 1
            department_counts[review.analysis.department_code] = (
                department_counts.get(review.analysis.department_code, 0) + 1
            )
            reputation_risk_score_total += review.analysis.reputation_risk_score
            reputation_risk_score_count += 1
        if review.rating is not None:
            rating_total += float(review.rating)
            rating_count += 1

    average_rating = round(rating_total / rating_count, 2) if rating_count else None
    average_reputation_risk_score = (
        round(reputation_risk_score_total / reputation_risk_score_count)
        if reputation_risk_score_count
        else 0
    )

    top_departments = [
        {"code": code, "count": count}
        for code, count in sorted(department_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    active_issues = session.scalar(
        select(func.count(DetectedIssue.id)).where(DetectedIssue.status == "active")
    ) or 0
    recurred_issues = session.scalar(
        select(func.count(DetectedIssue.id)).where(DetectedIssue.status == "recurred")
    ) or 0
    high_risk_issues = session.scalar(
        select(func.count(DetectedIssue.id)).where(DetectedIssue.reputation_risk_score >= 50)
    ) or 0

    all_issues = list(session.scalars(select(DetectedIssue)))
    priority_distribution: dict[str, int] = {}
    dept_issue_counts: dict[str, int] = {}
    for issue in all_issues:
        priority_distribution[issue.priority] = priority_distribution.get(issue.priority, 0) + 1
        dept_issue_counts[issue.department_code] = dept_issue_counts.get(issue.department_code, 0) + 1

    return OverviewKpiResponse(
        total_reviews=total,
        average_rating=average_rating,
        average_reputation_risk_score=average_reputation_risk_score,
        sentiment_mix=sentiment_mix,
        reputation_risk_mix=reputation_risk_mix,
        top_departments=top_departments,
        active_issues=active_issues,
        recurred_issues=recurred_issues,
        high_risk_issues=high_risk_issues,
        priority_distribution=priority_distribution,
        department_issue_counts=dept_issue_counts,
        filters_applied={
            "source_code": source_code,
            "department_code": department_code,
            "sentiment_label": sentiment_label,
            "reputation_risk": reputation_risk,
            "risk_group": risk_group,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    )


def _dashboard_filters(
    *,
    source_code: str | None = None,
    department_code: str | None = None,
    sentiment_label: str | None = None,
    reputation_risk: str | None = None,
    risk_group: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    search: str | None = None,
) -> dict[str, str | None]:
    return {
        "source_code": source_code,
        "department_code": department_code,
        "sentiment_label": sentiment_label,
        "reputation_risk": reputation_risk,
        "risk_group": risk_group,
        "date_from": date_from.date().isoformat() if date_from else None,
        "date_to": date_to.date().isoformat() if date_to else None,
        "search": search,
    }


def _dashboard_drill_through(path: str, filters: dict[str, str | None]) -> DashboardDrillThroughResponse:
    cleaned = {key: value for key, value in filters.items() if value not in (None, "")}
    return DashboardDrillThroughResponse(path=path, filters=cleaned)


@app.get("/overview/action-analytics", tags=["overview"], response_model=OverviewActionAnalyticsResponse)
async def overview_action_analytics(
    source_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    reputation_risk: str | None = Query(default=None),
    risk_group: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> OverviewActionAnalyticsResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if reputation_risk is not None and reputation_risk not in _VALID_REPUTATION_RISK_LABELS:
        raise HTTPException(status_code=422, detail=f"reputation_risk must be one of {sorted(_VALID_REPUTATION_RISK_LABELS)}")
    if risk_group is not None and risk_group not in {"high_or_critical"}:
        raise HTTPException(status_code=422, detail=f"risk_group must be 'high_or_critical'")

    base_filters = _dashboard_filters(
        source_code=source_code,
        department_code=department_code,
        sentiment_label=sentiment_label,
        reputation_risk=reputation_risk,
        risk_group=risk_group,
        date_from=date_from,
        date_to=date_to,
    )

    review_query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(selectinload(NormalizedReview.analysis))
    )
    review_query = review_query.where(NormalizedReview.source_code.in_(MVP_REVIEW_SOURCE_CODES))
    if source_code is not None:
        review_query = review_query.where(NormalizedReview.source_code == source_code)
    if department_code is not None:
        review_query = review_query.where(
            NormalizedReview.analysis.has(ReviewAnalysis.department_code == department_code)
        )
    if sentiment_label is not None:
        review_query = review_query.where(
            NormalizedReview.analysis.has(ReviewAnalysis.sentiment_label == sentiment_label)
        )
    if reputation_risk is not None:
        review_query = review_query.where(
            NormalizedReview.analysis.has(ReviewAnalysis.reputation_risk_label == reputation_risk)
        )
    if risk_group == "high_or_critical":
        review_query = review_query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.reputation_risk_label.in_(["high", "critical"])
            )
        )
    if date_from is not None:
        review_query = review_query.where(NormalizedReview.review_date >= date_from)
    if date_to is not None:
        review_query = review_query.where(NormalizedReview.review_date <= date_to)

    matched_reviews = list(session.scalars(review_query.order_by(NormalizedReview.review_date.desc())))

    high_risk_reviews = [
        r for r in matched_reviews
        if r.analysis is not None and r.analysis.reputation_risk_label in {"high", "critical"}
    ]
    action_leakage_reviews = high_risk_reviews

    active_issues = session.scalar(
        select(func.count(DetectedIssue.id)).where(DetectedIssue.status == "active")
    ) or 0
    high_risk_issues_count = session.scalar(
        select(func.count(DetectedIssue.id)).where(DetectedIssue.reputation_risk_score >= 50)
    ) or 0
    recurred_issues_count = session.scalar(
        select(func.count(DetectedIssue.id)).where(DetectedIssue.status == "recurred")
    ) or 0

    issues_by_department: dict[str, list[DetectedIssue]] = {}
    all_issues = list(session.scalars(select(DetectedIssue)))
    for issue in all_issues:
        issues_by_department.setdefault(issue.department_code, []).append(issue)

    owner_pressure: list[DashboardOwnerPressureItemResponse] = []
    for dept_code, dept_issues in issues_by_department.items():
        active_count = sum(1 for i in dept_issues if i.status == "active")
        high_risk_dept = sum(1 for i in dept_issues if i.reputation_risk_score >= 50)
        owner_pressure.append(
            DashboardOwnerPressureItemResponse(
                department_code=dept_code,
                active_issues=active_count,
                high_risk_issues=high_risk_dept,
                issues_drill_through=_dashboard_drill_through(
                    "/issues",
                    {"department_code": dept_code},
                ),
                reviews_drill_through=_dashboard_drill_through(
                    "/reviews",
                    {"department_code": dept_code, "risk_group": "high_or_critical"},
                ),
            )
        )
    owner_pressure.sort(key=lambda item: (item.high_risk_issues, item.active_issues), reverse=True)

    platform_counts: dict[str, int] = {}
    for review in high_risk_reviews:
        platform_counts[review.source_code] = platform_counts.get(review.source_code, 0) + 1

    platform_risk_spread = [
        DashboardPlatformRiskItemResponse(
            source_code=src,
            high_risk_reviews=count,
            drill_through=_dashboard_drill_through(
                "/reviews",
                {"source_code": src, "risk_group": "high_or_critical"},
            ),
        )
        for src, count in platform_counts.items()
    ]
    platform_risk_spread.sort(key=lambda item: item.high_risk_reviews, reverse=True)

    recent_issues = sorted(
        all_issues,
        key=lambda i: i.last_seen_at or i.created_at,
        reverse=True,
    )[:5]
    recent_issue_items = [
        DashboardIssueItemResponse(
            issue_id=issue.id,
            title=issue.title,
            department_code=issue.department_code,
            status=issue.status,
            priority=issue.priority,
            reputation_risk_score=issue.reputation_risk_score,
            recurrence_count=issue.recurrence_count,
            first_seen_at=issue.first_seen_at,
            last_seen_at=issue.last_seen_at,
            issues_drill_through=_dashboard_drill_through("/issues", {}),
            reviews_drill_through=_dashboard_drill_through(
                "/reviews",
                {"department_code": issue.department_code},
            ),
        )
        for issue in recent_issues
    ]

    return OverviewActionAnalyticsResponse(
        active_issues=DashboardIssueMetricResponse(
            issue_count=active_issues,
            drill_through=_dashboard_drill_through("/issues", {"status": "active"}),
        ),
        high_risk_issues=DashboardIssueMetricResponse(
            issue_count=high_risk_issues_count,
            drill_through=_dashboard_drill_through("/issues", {"min_risk": "50"}),
        ),
        recurred_issues=DashboardIssueMetricResponse(
            issue_count=recurred_issues_count,
            drill_through=_dashboard_drill_through("/issues", {"status": "recurred"}),
        ),
        action_leakage=DashboardActionMetricResponse(
            review_count=len(action_leakage_reviews),
            drill_through=_dashboard_drill_through(
                "/reviews",
                {"risk_group": "high_or_critical"},
            ),
        ),
        aging_risk=DashboardAgingRiskResponse(
            review_count=0,
            threshold_days=7,
            oldest_review_date=None,
            drill_through=_dashboard_drill_through("/reviews", {}),
        ),
        owner_pressure=owner_pressure[:5],
        platform_risk_spread=platform_risk_spread[:3],
        recent_issues=recent_issue_items,
        filters_applied={
            "source_code": source_code,
            "department_code": department_code,
            "sentiment_label": sentiment_label,
            "reputation_risk": reputation_risk,
            "risk_group": risk_group,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    )
