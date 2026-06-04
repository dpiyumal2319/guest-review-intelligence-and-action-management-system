from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.analysis import reanalyze_reviews
from app.analysis_runtime import AnalysisRuntimeUnavailableError
from app.connectors.registry import CONNECTORS
from app.database import get_session
from app.ingestion import run_mock_connector_by_key
from app.models import (
    ActionTicket,
    CategoryDepartmentMapping,
    DemoRole,
    Department,
    IngestionRun,
    IssueCategory,
    NormalizedReview,
    ReviewAnalysis,
    ReviewIssueCategoryPrediction,
    ReviewSource,
    ReputationRiskThreshold,
    TicketEvent,
)
from app.schemas import (
    ConnectorImportRequest,
    HealthResponse,
    IngestionRunResponse,
    IngestionRunsResponse,
    IngestionSourceStatusesResponse,
    IssueSummaryResponse,
    IssueSummaryItemResponse,
    ReferenceConfigResponse,
    OverviewKpiResponse,
    ReanalysisResponse,
    RecurringIssueTicketCreateRequest,
    ReviewResponse,
    ReviewsResponse,
    SemanticAnalysisResponse,
    TicketCreateRequest,
    TicketResponse,
    TicketsResponse,
    TicketUpdateRequest,
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
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        issue_categories=list(session.scalars(select(IssueCategory).order_by(IssueCategory.sort_order))),
        category_department_mappings=list(
            session.scalars(
                select(CategoryDepartmentMapping).order_by(
                    CategoryDepartmentMapping.category_code,
                    CategoryDepartmentMapping.is_primary.desc(),
                    CategoryDepartmentMapping.department_code,
                )
            )
        ),
        reputation_risk_thresholds=list(session.scalars(select(ReputationRiskThreshold).order_by(ReputationRiskThreshold.category_code))),
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
    issue_category_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    reputation_risk: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1),
    session: Session = Depends(get_session),
) -> ReviewsResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if reputation_risk is not None and reputation_risk not in _VALID_REPUTATION_RISK_LABELS:
        raise HTTPException(status_code=422, detail=f"reputation_risk must be one of {sorted(_VALID_REPUTATION_RISK_LABELS)}")
    if action_status is not None and action_status not in _VALID_REVIEW_ACTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"action_status must be one of {sorted(_VALID_REVIEW_ACTION_STATUSES)}")

    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(
            selectinload(NormalizedReview.source),
            selectinload(NormalizedReview.analysis).selectinload(ReviewAnalysis.issue_category_predictions),
        )
    )
    query = query.where(ReviewSource.source_type == "verified_review")
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)
    if issue_category_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.category_code == issue_category_code
                )
            )
        )
    if department_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.department_code == department_code
                )
            )
        )
    if sentiment_label is not None:
        query = query.where(NormalizedReview.sentiment_label == sentiment_label)
    if reputation_risk is not None:
        query = query.where(NormalizedReview.reputation_risk == reputation_risk)
    if action_status is not None:
        query = query.where(NormalizedReview.action_status == action_status)
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

    imported_reviews = list(session.scalars(query.order_by(NormalizedReview.review_date.desc())))
    review_payloads = []
    for review in imported_reviews:
        payload = ReviewResponse.model_validate(review).model_dump()
        if payload["analysis"] is not None:
            payload["analysis"]["explanation_factors"].pop("model", None)
        review_payloads.append(payload)
    return ReviewsResponse(reviews=review_payloads)


@app.get("/analysis/semantic-clusters", tags=["analysis"], response_model=SemanticAnalysisResponse)
async def semantic_clusters(
    source_code: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    similarity_threshold: float = Query(default=DEFAULT_SIMILARITY_THRESHOLD, ge=0.0, le=1.0),
    min_cluster_size: int = Query(default=DEFAULT_MIN_CLUSTER_SIZE, ge=2, le=20),
    session: Session = Depends(get_session),
) -> SemanticAnalysisResponse:
    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(
            selectinload(NormalizedReview.source),
            selectinload(NormalizedReview.analysis).selectinload(ReviewAnalysis.issue_category_predictions),
        )
    )
    query = query.where(ReviewSource.source_type == "verified_review")
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)
    if issue_category_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.category_code == issue_category_code
                )
            )
        )
    if department_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.department_code == department_code
                )
            )
        )

    imported_reviews = list(session.scalars(query.order_by(NormalizedReview.review_date.desc(), NormalizedReview.id)))
    semantic_result = analyze_semantic_similarity(
        imported_reviews,
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
    )
    response = SemanticAnalysisResponse.model_validate(asdict(semantic_result))
    cluster_ticket_ids = _ticket_ids_by_source_group(session, "semantic_cluster")
    for cluster in response.clusters:
        cluster.linked_ticket_ids = cluster_ticket_ids.get(cluster.cluster_id, [])
    return response


@app.post("/analysis/reanalyze", tags=["analysis"], response_model=ReanalysisResponse)
async def reanalyze_imported_reviews(
    source_code: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ReanalysisResponse:
    try:
        analyzed_count = reanalyze_reviews(session, source_code=source_code, source_type="verified_review")
    except AnalysisRuntimeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ReanalysisResponse(analyzed_count=analyzed_count)


_VALID_TICKET_STATUSES = {"open", "in_progress", "blocked", "resolved", "verified"}
_VALID_TICKET_PRIORITIES = {"low", "medium", "high", "urgent"}
_VALID_REVIEW_ACTION_STATUSES = {"new", "reviewed", "ticket_created", "ignored"}
_VALID_SENTIMENT_LABELS = {"positive", "mixed", "negative"}
_VALID_REPUTATION_RISK_LABELS = {"low", "medium", "high", "critical"}
_ALLOWED_TICKET_STATUS_TRANSITIONS = {
    "open": {"in_progress", "blocked", "resolved"},
    "in_progress": {"open", "blocked", "resolved"},
    "blocked": {"open", "in_progress", "resolved"},
    "resolved": {"open", "in_progress", "blocked", "verified"},
    "verified": set(),
}


def _ticket_ids_by_source_group(session: Session, source_group_type: str) -> dict[str, list[int]]:
    tickets = list(
        session.scalars(
            select(ActionTicket)
            .where(ActionTicket.source_group_type == source_group_type)
            .order_by(ActionTicket.created_at.desc())
        )
    )
    linked: dict[str, list[int]] = {}
    for ticket in tickets:
        if ticket.source_group_key is None:
            continue
        linked.setdefault(ticket.source_group_key, []).append(ticket.id)
    return linked


def _validate_recurring_ticket_request(body: RecurringIssueTicketCreateRequest, session: Session) -> None:
    if body.priority is not None and body.priority not in _VALID_TICKET_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"priority must be one of {sorted(_VALID_TICKET_PRIORITIES)}")
    if body.department_code is not None and session.scalar(
        select(Department).where(Department.code == body.department_code)
    ) is None:
        raise HTTPException(status_code=422, detail=f"Unknown department '{body.department_code}'")


def _dominant_department(reviews: list[NormalizedReview]) -> str:
    counts: dict[str, int] = {}
    for review in reviews:
        counts[review.department_code] = counts.get(review.department_code, 0) + 1
    return max(counts, key=lambda department: counts[department])


def _priority_from_reputation_risk_label(label: str | None) -> str:
    if label == "critical":
        return "urgent"
    if label == "high":
        return "high"
    if label == "medium":
        return "medium"
    return "low"


def _priority_from_review(review: NormalizedReview) -> str:
    label = review.analysis.reputation_risk_label if review.analysis is not None else review.reputation_risk
    return _priority_from_reputation_risk_label(label)


def _priority_from_reviews(reviews: list[NormalizedReview]) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    highest_label = max(
        (
            review.analysis.reputation_risk_label if review.analysis is not None else review.reputation_risk
            for review in reviews
        ),
        key=lambda label: order.get(label, 0),
        default="low",
    )
    return _priority_from_reputation_risk_label(highest_label)


def _validate_ticket_status_transition(current_status: str, next_status: str) -> None:
    if next_status == current_status:
        return
    allowed_next = _ALLOWED_TICKET_STATUS_TRANSITIONS.get(current_status, set())
    if next_status not in allowed_next:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot transition ticket from {current_status} to {next_status}",
        )


def _assignment_value(name: str | None, email: str | None) -> str | None:
    if name and email:
        return f"{name} <{email}>"
    return name or email


def _filtered_verified_reviews_query(
    *,
    source_code: str | None = None,
    issue_category_code: str | None = None,
    department_code: str | None = None,
    sentiment_label: str | None = None,
    reputation_risk: str | None = None,
    action_status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(
            selectinload(NormalizedReview.source),
            selectinload(NormalizedReview.analysis).selectinload(ReviewAnalysis.issue_category_predictions),
            selectinload(NormalizedReview.issue_category),
        )
    )
    query = query.where(ReviewSource.source_type == "verified_review")
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)
    if issue_category_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.category_code == issue_category_code
                )
            )
        )
    if department_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.department_code == department_code
                )
            )
        )
    if sentiment_label is not None:
        query = query.where(NormalizedReview.sentiment_label == sentiment_label)
    if reputation_risk is not None:
        query = query.where(NormalizedReview.reputation_risk == reputation_risk)
    if action_status is not None:
        query = query.where(NormalizedReview.action_status == action_status)
    if date_from is not None:
        query = query.where(NormalizedReview.review_date >= date_from)
    if date_to is not None:
        query = query.where(NormalizedReview.review_date <= date_to)
    return query


def _create_recurring_issue_ticket(
    *,
    session: Session,
    body: RecurringIssueTicketCreateRequest,
    priority: str,
    department_code: str,
    source_group_type: str,
    source_group_key: str,
    source_group_label: str,
    source_category_code: str,
    source_cluster_id: str | None,
    source_review_ids: list[int],
    note_prefix: str,
) -> ActionTicket:
    now = datetime.now(timezone.utc)
    ticket = ActionTicket(
        review_id=None,
        department_code=department_code,
        source_group_type=source_group_type,
        source_group_key=source_group_key,
        source_group_label=source_group_label,
        source_category_code=source_category_code,
        source_cluster_id=source_cluster_id,
        source_review_ids=source_review_ids,
        priority=priority,
        status="open",
        assignee_name=body.assignee_name,
        assignee_email=body.assignee_email,
        due_date=body.due_date,
        notes=body.notes,
        created_at=now,
        updated_at=now,
    )
    session.add(ticket)

    for review_id in source_review_ids:
        review = session.get(NormalizedReview, review_id)
        if review is not None:
            review.action_status = "ticket_created"
            review.updated_at = now

    session.flush()
    note = f"{note_prefix}; source reviews: {', '.join(f'#{review_id}' for review_id in source_review_ids)}"
    if body.notes:
        note = f"{note}. {body.notes}"
    session.add(TicketEvent(
        ticket_id=ticket.id,
        event_type="created",
        old_value=None,
        new_value="open",
        note=note,
        occurred_at=now,
    ))
    session.commit()
    session.refresh(ticket)
    return ticket


@app.get("/overview/kpis", tags=["overview"], response_model=OverviewKpiResponse)
async def overview_kpis(
    source_code: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    reputation_risk: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> OverviewKpiResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if reputation_risk is not None and reputation_risk not in _VALID_REPUTATION_RISK_LABELS:
        raise HTTPException(status_code=422, detail=f"reputation_risk must be one of {sorted(_VALID_REPUTATION_RISK_LABELS)}")
    if action_status is not None and action_status not in _VALID_REVIEW_ACTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"action_status must be one of {sorted(_VALID_REVIEW_ACTION_STATUSES)}")

    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(selectinload(NormalizedReview.analysis))
    )
    query = query.where(ReviewSource.source_type == "verified_review")
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)
    if issue_category_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.category_code == issue_category_code
                )
            )
        )
    if department_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.department_code == department_code
                )
            )
        )
    if sentiment_label is not None:
        query = query.where(NormalizedReview.sentiment_label == sentiment_label)
    if reputation_risk is not None:
        query = query.where(NormalizedReview.reputation_risk == reputation_risk)
    if action_status is not None:
        query = query.where(NormalizedReview.action_status == action_status)
    if date_from is not None:
        query = query.where(NormalizedReview.review_date >= date_from)
    if date_to is not None:
        query = query.where(NormalizedReview.review_date <= date_to)

    matched_reviews = list(session.scalars(query))
    total = len(matched_reviews)

    sentiment_mix = {label: 0 for label in _VALID_SENTIMENT_LABELS}
    reputation_risk_mix = {label: 0 for label in _VALID_REPUTATION_RISK_LABELS}
    action_status_mix = {label: 0 for label in _VALID_REVIEW_ACTION_STATUSES}
    department_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    rating_total = 0.0
    rating_count = 0
    reputation_risk_score_total = 0
    reputation_risk_score_count = 0

    for review in matched_reviews:
        if review.sentiment_label in sentiment_mix:
            sentiment_mix[review.sentiment_label] += 1
        if review.reputation_risk in reputation_risk_mix:
            reputation_risk_mix[review.reputation_risk] += 1
        if review.action_status in action_status_mix:
            action_status_mix[review.action_status] += 1
        if review.rating is not None:
            rating_total += float(review.rating)
            rating_count += 1
        if review.department_code:
            department_counts[review.department_code] = department_counts.get(review.department_code, 0) + 1
        if review.issue_category_code:
            category_counts[review.issue_category_code] = category_counts.get(review.issue_category_code, 0) + 1
        if review.analysis is not None:
            reputation_risk_score_total += review.analysis.reputation_risk_score
            reputation_risk_score_count += 1

    average_rating = round(rating_total / rating_count, 2) if rating_count else None
    average_reputation_risk_score = round(reputation_risk_score_total / reputation_risk_score_count) if reputation_risk_score_count else 0

    top_departments = [
        {"code": code, "count": count}
        for code, count in sorted(department_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    ]
    top_categories = [
        {"code": code, "count": count}
        for code, count in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    return OverviewKpiResponse(
        total_reviews=total,
        average_rating=average_rating,
        average_reputation_risk_score=average_reputation_risk_score,
        sentiment_mix=sentiment_mix,
        reputation_risk_mix=reputation_risk_mix,
        action_status_mix=action_status_mix,
        top_departments=top_departments,
        top_categories=top_categories,
        filters_applied={
            "source_code": source_code,
            "issue_category_code": issue_category_code,
            "department_code": department_code,
            "sentiment_label": sentiment_label,
            "reputation_risk": reputation_risk,
            "action_status": action_status,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    )


@app.get("/issues/summary", tags=["issues"], response_model=IssueSummaryResponse)
async def issues_summary(
    source_code: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    reputation_risk: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> IssueSummaryResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if reputation_risk is not None and reputation_risk not in _VALID_REPUTATION_RISK_LABELS:
        raise HTTPException(status_code=422, detail=f"reputation_risk must be one of {sorted(_VALID_REPUTATION_RISK_LABELS)}")
    if action_status is not None and action_status not in _VALID_REVIEW_ACTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"action_status must be one of {sorted(_VALID_REVIEW_ACTION_STATUSES)}")

    query = _filtered_verified_reviews_query(
        source_code=source_code,
        issue_category_code=issue_category_code,
        department_code=department_code,
        sentiment_label=sentiment_label,
        reputation_risk=reputation_risk,
        action_status=action_status,
        date_from=date_from,
        date_to=date_to,
    )

    matched_reviews = list(session.scalars(query.order_by(NormalizedReview.review_date.desc(), NormalizedReview.id)))
    total = len(matched_reviews)

    most_recent_review_date = max(
        (review.review_date for review in matched_reviews if review.review_date is not None),
        default=None,
    )
    recent_window_start = most_recent_review_date - timedelta(days=14) if most_recent_review_date is not None else None

    grouped_aggregates: dict[tuple[str, str], dict] = {}
    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    for review in matched_reviews:
        cat_code = review.issue_category_code
        dept_code = review.department_code
        group_key = (cat_code, dept_code)
        if group_key not in grouped_aggregates:
            grouped_aggregates[group_key] = {
                "group_key": f"{cat_code}:{dept_code}",
                "category_code": cat_code,
                "category_name": review.issue_category.name if review.issue_category else cat_code.replace("_", " ").title(),
                "department_code": dept_code,
                "review_count": 0,
                "recent_review_count": 0,
                "reputation_risk_score_total": 0,
                "reputation_risk_score_count": 0,
                "highest_reputation_risk": "low",
                "source_mix": {},
                "min_review_id": review.id,
                "latest_review_date": review.review_date,
            }
        agg = grouped_aggregates[group_key]
        agg["review_count"] += 1
        if recent_window_start is not None and review.review_date is not None and review.review_date >= recent_window_start:
            agg["recent_review_count"] += 1
        if review.analysis is not None:
            agg["reputation_risk_score_total"] += review.analysis.reputation_risk_score
            agg["reputation_risk_score_count"] += 1
        review_risk_label = review.analysis.reputation_risk_label if review.analysis is not None else review.reputation_risk
        if risk_order.get(review_risk_label, 0) > risk_order.get(agg["highest_reputation_risk"], 0):
            agg["highest_reputation_risk"] = review_risk_label
        src = review.source_code
        agg["source_mix"][src] = agg["source_mix"].get(src, 0) + 1
        if review.id < agg["min_review_id"]:
            agg["min_review_id"] = review.id
        if agg["latest_review_date"] is None or (
            review.review_date is not None and review.review_date > agg["latest_review_date"]
        ):
            agg["latest_review_date"] = review.review_date

    category_ticket_ids = _ticket_ids_by_source_group(session, "category_department_recurrence")
    items: list[IssueSummaryItemResponse] = []
    for agg in sorted(
        grouped_aggregates.values(),
        key=lambda x: (x["recent_review_count"], x["review_count"], x["average_reputation_risk_score"] if "average_reputation_risk_score" in x else 0),
        reverse=True,
    ):
        avg_reputation_risk = (
            round(agg["reputation_risk_score_total"] / agg["reputation_risk_score_count"], 1)
            if agg["reputation_risk_score_count"] > 0
            else 0.0
        )
        items.append(IssueSummaryItemResponse(
            group_key=agg["group_key"],
            category_code=agg["category_code"],
            category_name=agg["category_name"],
            department_code=agg["department_code"],
            review_count=agg["review_count"],
            recent_review_count=agg["recent_review_count"],
            average_reputation_risk_score=avg_reputation_risk,
            highest_reputation_risk=agg["highest_reputation_risk"],
            source_mix=agg["source_mix"],
            representative_review_id=agg["min_review_id"],
            latest_review_date=agg["latest_review_date"],
            linked_ticket_ids=category_ticket_ids.get(agg["group_key"], []),
        ))

    return IssueSummaryResponse(
        items=items,
        total_reviews=total,
        filters_applied={
            "source_code": source_code,
            "issue_category_code": issue_category_code,
            "department_code": department_code,
            "sentiment_label": sentiment_label,
            "reputation_risk": reputation_risk,
            "action_status": action_status,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    )


@app.post("/issues/groups/{category_code}/{department_code}/tickets", tags=["tickets"], response_model=TicketResponse, status_code=201)
async def create_issue_group_ticket(
    category_code: str,
    department_code: str,
    body: RecurringIssueTicketCreateRequest,
    source_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    reputation_risk: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ActionTicket:
    category = session.get(IssueCategory, category_code)
    if category is None:
        raise HTTPException(status_code=404, detail="Issue category not found")
    _validate_recurring_ticket_request(body, session)
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if reputation_risk is not None and reputation_risk not in _VALID_REPUTATION_RISK_LABELS:
        raise HTTPException(status_code=422, detail=f"reputation_risk must be one of {sorted(_VALID_REPUTATION_RISK_LABELS)}")
    if action_status is not None and action_status not in _VALID_REVIEW_ACTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"action_status must be one of {sorted(_VALID_REVIEW_ACTION_STATUSES)}")

    query = _filtered_verified_reviews_query(
        source_code=source_code,
        issue_category_code=category_code,
        department_code=department_code,
        sentiment_label=sentiment_label,
        reputation_risk=reputation_risk,
        action_status=action_status,
        date_from=date_from,
        date_to=date_to,
    )

    reviews = list(session.scalars(query.order_by(NormalizedReview.review_date.desc(), NormalizedReview.id)))
    reviews = [review for review in reviews if review.department_code == department_code]
    if not reviews:
        raise HTTPException(status_code=404, detail="No reviews found for this recurring issue group")

    affected_department = body.department_code or department_code
    return _create_recurring_issue_ticket(
        session=session,
        body=body,
        priority=body.priority or _priority_from_reviews(reviews),
        department_code=affected_department,
        source_group_type="category_department_recurrence",
        source_group_key=f"{category_code}:{department_code}",
        source_group_label=f"{category.name} recurrence for {department_code.replace('_', ' ')}",
        source_category_code=category_code,
        source_cluster_id=None,
        source_review_ids=[review.id for review in reviews],
        note_prefix=f"Created from recurring issue group {category.name} / {department_code.replace('_', ' ')}",
    )


@app.post("/analysis/semantic-clusters/{cluster_id}/tickets", tags=["tickets"], response_model=TicketResponse, status_code=201)
async def create_semantic_cluster_ticket(
    cluster_id: str,
    body: RecurringIssueTicketCreateRequest,
    source_code: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    similarity_threshold: float = Query(default=DEFAULT_SIMILARITY_THRESHOLD, ge=0.0, le=1.0),
    min_cluster_size: int = Query(default=DEFAULT_MIN_CLUSTER_SIZE, ge=2, le=20),
    session: Session = Depends(get_session),
) -> ActionTicket:
    _validate_recurring_ticket_request(body, session)
    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(
            selectinload(NormalizedReview.source),
            selectinload(NormalizedReview.analysis).selectinload(ReviewAnalysis.issue_category_predictions),
        )
    )
    query = query.where(ReviewSource.source_type == "verified_review")
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)
    if issue_category_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.category_code == issue_category_code
                )
            )
        )
    if department_code is not None:
        query = query.where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.department_code == department_code
                )
            )
        )

    reviews = list(session.scalars(query.order_by(NormalizedReview.review_date.desc(), NormalizedReview.id)))
    analysis = analyze_semantic_similarity(
        reviews,
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
    )
    cluster = next((item for item in analysis.clusters if item.cluster_id == cluster_id), None)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Semantic cluster not found with the current filters")

    category = session.get(IssueCategory, cluster.category_code)
    label = category.name if category is not None else cluster.category_code.replace("_", " ").title()
    return _create_recurring_issue_ticket(
        session=session,
        body=body,
        priority=body.priority or _priority_from_reviews([review for review in reviews if review.id in cluster.review_ids]),
        department_code=body.department_code or cluster.department_code,
        source_group_type="semantic_cluster",
        source_group_key=cluster.cluster_id,
        source_group_label=f"{label} semantic cluster",
        source_category_code=cluster.category_code,
        source_cluster_id=cluster.cluster_id,
        source_review_ids=cluster.review_ids,
        note_prefix=f"Created from semantic cluster {cluster.cluster_id}",
    )


@app.post("/reviews/{review_id}/tickets", tags=["tickets"], response_model=TicketResponse, status_code=201)
async def create_ticket(
    review_id: int,
    body: TicketCreateRequest,
    session: Session = Depends(get_session),
) -> ActionTicket:
    review = session.get(NormalizedReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    if body.priority is not None and body.priority not in _VALID_TICKET_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"priority must be one of {sorted(_VALID_TICKET_PRIORITIES)}")
    if session.scalar(select(Department).where(Department.code == body.department_code)) is None:
        raise HTTPException(status_code=422, detail=f"Unknown department '{body.department_code}'")

    now = datetime.now(timezone.utc)
    ticket = ActionTicket(
        review_id=review_id,
        department_code=body.department_code,
        priority=body.priority or _priority_from_review(review),
        status="open",
        assignee_name=body.assignee_name,
        assignee_email=body.assignee_email,
        due_date=body.due_date,
        notes=body.notes,
        created_at=now,
        updated_at=now,
    )
    session.add(ticket)

    review.action_status = "ticket_created"
    review.updated_at = now

    session.flush()

    session.add(TicketEvent(
        ticket_id=ticket.id,
        event_type="created",
        old_value=None,
        new_value="open",
        note=body.notes,
        occurred_at=now,
    ))
    session.commit()
    session.refresh(ticket)
    return ticket


@app.get("/reviews/{review_id}/tickets", tags=["tickets"], response_model=TicketsResponse)
async def review_tickets(
    review_id: int,
    session: Session = Depends(get_session),
) -> TicketsResponse:
    if session.get(NormalizedReview, review_id) is None:
        raise HTTPException(status_code=404, detail="Review not found")
    tickets = list(
        session.scalars(
            select(ActionTicket)
            .where(ActionTicket.review_id == review_id)
            .options(selectinload(ActionTicket.events))
            .order_by(ActionTicket.created_at.desc())
        )
    )
    return TicketsResponse(tickets=tickets)


@app.get("/tickets", tags=["tickets"], response_model=TicketsResponse)
async def list_tickets(
    department_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    reputation_risk: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> TicketsResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if reputation_risk is not None and reputation_risk not in _VALID_REPUTATION_RISK_LABELS:
        raise HTTPException(status_code=422, detail=f"reputation_risk must be one of {sorted(_VALID_REPUTATION_RISK_LABELS)}")
    if action_status is not None and action_status not in _VALID_REVIEW_ACTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"action_status must be one of {sorted(_VALID_REVIEW_ACTION_STATUSES)}")

    needs_review_join = any(v is not None for v in [sentiment_label, reputation_risk, issue_category_code, action_status])

    if needs_review_join:
        query = (
            select(ActionTicket)
            .outerjoin(NormalizedReview, ActionTicket.review_id == NormalizedReview.id)
            .options(selectinload(ActionTicket.events))
        )
    else:
        query = select(ActionTicket).options(selectinload(ActionTicket.events))

    if department_code is not None:
        query = query.where(ActionTicket.department_code == department_code)
    if status is not None:
        query = query.where(ActionTicket.status == status)
    if priority is not None:
        query = query.where(ActionTicket.priority == priority)
    if date_from is not None:
        query = query.where(ActionTicket.created_at >= date_from)
    if date_to is not None:
        query = query.where(ActionTicket.created_at <= date_to)
    if sentiment_label is not None:
        query = query.where(NormalizedReview.sentiment_label == sentiment_label)
    if reputation_risk is not None:
        query = query.where(NormalizedReview.reputation_risk == reputation_risk)
    if issue_category_code is not None:
        query = query.where(
            or_(
                NormalizedReview.issue_category_code == issue_category_code,
                ActionTicket.source_category_code == issue_category_code,
            )
        )
    if action_status is not None:
        query = query.where(NormalizedReview.action_status == action_status)

    tickets = list(session.scalars(query.order_by(ActionTicket.created_at.desc())))
    return TicketsResponse(tickets=tickets)


@app.get("/tickets/{ticket_id}", tags=["tickets"], response_model=TicketResponse)
async def get_ticket(
    ticket_id: int,
    session: Session = Depends(get_session),
) -> ActionTicket:
    ticket = session.scalar(
        select(ActionTicket)
        .where(ActionTicket.id == ticket_id)
        .options(selectinload(ActionTicket.events))
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@app.patch("/tickets/{ticket_id}", tags=["tickets"], response_model=TicketResponse)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdateRequest,
    session: Session = Depends(get_session),
) -> ActionTicket:
    ticket = session.scalar(
        select(ActionTicket)
        .where(ActionTicket.id == ticket_id)
        .options(selectinload(ActionTicket.events))
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    now = datetime.now(timezone.utc)
    events: list[TicketEvent] = []
    explicitly_set_fields = body.model_fields_set

    if body.status is not None and body.status != ticket.status:
        if body.status not in _VALID_TICKET_STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be one of {sorted(_VALID_TICKET_STATUSES)}")
        _validate_ticket_status_transition(ticket.status, body.status)
        events.append(TicketEvent(ticket_id=ticket_id, event_type="status_change", old_value=ticket.status, new_value=body.status, occurred_at=now))
        ticket.status = body.status

    if body.priority is not None and body.priority != ticket.priority:
        if body.priority not in _VALID_TICKET_PRIORITIES:
            raise HTTPException(status_code=422, detail=f"priority must be one of {sorted(_VALID_TICKET_PRIORITIES)}")
        events.append(TicketEvent(ticket_id=ticket_id, event_type="priority_change", old_value=ticket.priority, new_value=body.priority, occurred_at=now))
        ticket.priority = body.priority

    if body.department_code is not None and body.department_code != ticket.department_code:
        if session.scalar(select(Department).where(Department.code == body.department_code)) is None:
            raise HTTPException(status_code=422, detail=f"Unknown department '{body.department_code}'")
        events.append(TicketEvent(ticket_id=ticket_id, event_type="department_change", old_value=ticket.department_code, new_value=body.department_code, occurred_at=now))
        ticket.department_code = body.department_code

    if "assignee_name" in explicitly_set_fields or "assignee_email" in explicitly_set_fields:
        next_assignee_name = body.assignee_name if "assignee_name" in explicitly_set_fields else ticket.assignee_name
        next_assignee_email = body.assignee_email if "assignee_email" in explicitly_set_fields else ticket.assignee_email
        old_assignee = _assignment_value(ticket.assignee_name, ticket.assignee_email)
        new_assignee = _assignment_value(next_assignee_name, next_assignee_email)
        if old_assignee != new_assignee:
            events.append(
                TicketEvent(
                    ticket_id=ticket_id,
                    event_type="assignment_change",
                    old_value=old_assignee,
                    new_value=new_assignee,
                    occurred_at=now,
                )
            )
            ticket.assignee_name = next_assignee_name
            ticket.assignee_email = next_assignee_email

    if body.notes is not None:
        events.append(TicketEvent(ticket_id=ticket_id, event_type="note_added", old_value=None, new_value=None, note=body.notes, occurred_at=now))
        ticket.notes = body.notes

    if "due_date" in explicitly_set_fields and body.due_date != ticket.due_date:
        events.append(
            TicketEvent(
                ticket_id=ticket_id,
                event_type="due_date_change",
                old_value=ticket.due_date.isoformat() if ticket.due_date else None,
                new_value=body.due_date.isoformat() if body.due_date else None,
                occurred_at=now,
            )
        )
        ticket.due_date = body.due_date

    if events:
        ticket.updated_at = now
        session.add_all(events)

    session.commit()
    session.refresh(ticket)
    return ticket
