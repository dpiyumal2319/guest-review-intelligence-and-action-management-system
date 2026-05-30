from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.apify_importer import ApifyImportInput, run_apify_dataset_import
from app.analysis import reanalyze_reviews
from app.connectors.registry import CONNECTORS
from app.database import get_session
from app.ingestion import run_mock_connector_by_key, run_seed_ingestion
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
    SeverityThreshold,
    TicketEvent,
)
from app.reddit_import import run_reddit_social_listening_ingestion
from app.schemas import (
    ApifyDatasetImportRequest,
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
        review_sources=list(session.scalars(select(ReviewSource).order_by(ReviewSource.code))),
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
        severity_thresholds=list(session.scalars(select(SeverityThreshold).order_by(SeverityThreshold.category_code))),
        demo_roles=list(session.scalars(select(DemoRole).order_by(DemoRole.code))),
    )


@app.post("/ingestion/seed", tags=["ingestion"], response_model=IngestionRunResponse)
async def import_seed_reviews(session: Session = Depends(get_session)) -> IngestionRun:
    return run_seed_ingestion(session)


@app.post("/ingestion/connectors/{connector_key}", tags=["ingestion"], response_model=IngestionRunResponse)
async def import_verified_connector(connector_key: str, session: Session = Depends(get_session)) -> IngestionRun:
    if connector_key not in CONNECTORS:
        raise HTTPException(status_code=404, detail=f"Unknown connector '{connector_key}'")
    return run_mock_connector_by_key(session, connector_key)


@app.post(
    "/ingestion/apify-dataset",
    tags=["ingestion"],
    response_model=IngestionRunResponse,
    summary="Import an offline Apify dataset export",
    description=(
        "Loads a JSON or CSV file prepared outside the app for research/demo dataset preparation. "
        "This is not a production Apify connector or live scraping integration."
    ),
)
async def import_apify_dataset(
    request: ApifyDatasetImportRequest,
    session: Session = Depends(get_session),
) -> IngestionRun:
    return run_apify_dataset_import(session, ApifyImportInput(**request.model_dump()))


@app.post("/ingestion/reddit", tags=["ingestion"], response_model=IngestionRunResponse)
async def import_reddit_social_listening(session: Session = Depends(get_session)) -> IngestionRun:
    return run_reddit_social_listening_ingestion(session)


@app.get("/ingestion/runs", tags=["ingestion"], response_model=IngestionRunsResponse)
async def ingestion_runs(session: Session = Depends(get_session)) -> IngestionRunsResponse:
    runs = list(session.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(10)))
    return IngestionRunsResponse(runs=runs)


@app.get("/ingestion/source-status", tags=["ingestion"], response_model=IngestionSourceStatusesResponse)
async def ingestion_source_status(session: Session = Depends(get_session)) -> IngestionSourceStatusesResponse:
    sources = list(session.scalars(select(ReviewSource).order_by(ReviewSource.code)))
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
                "source_type": source.source_type,
                "is_verified_channel": source.is_verified_channel,
                "latest_run": latest_run,
                "errors": latest_run.errors if latest_run is not None else [],
            }
        )
    return IngestionSourceStatusesResponse(sources=statuses)


@app.get("/reviews", tags=["reviews"], response_model=ReviewsResponse)
async def reviews(
    source_type: str | None = Query(default=None),
    source_code: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1),
    include_social_listening: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> ReviewsResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if severity is not None and severity not in _VALID_SEVERITY_LABELS:
        raise HTTPException(status_code=422, detail=f"severity must be one of {sorted(_VALID_SEVERITY_LABELS)}")
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
    if source_type is not None:
        query = query.where(ReviewSource.source_type == source_type)
    elif not include_social_listening:
        query = query.where(ReviewSource.source_type != "social_listening")
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
    if severity is not None:
        query = query.where(NormalizedReview.severity == severity)
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
    return ReviewsResponse(reviews=imported_reviews)


@app.get("/analysis/semantic-clusters", tags=["analysis"], response_model=SemanticAnalysisResponse)
async def semantic_clusters(
    source_type: str | None = Query(default=None),
    source_code: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    include_social_listening: bool = Query(default=False),
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
    if source_type is not None:
        query = query.where(ReviewSource.source_type == source_type)
    elif not include_social_listening:
        query = query.where(ReviewSource.source_type != "social_listening")
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
    source_type: str | None = Query(default=None),
    source_code: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ReanalysisResponse:
    return ReanalysisResponse(analyzed_count=reanalyze_reviews(session, source_code=source_code, source_type=source_type))


_VALID_TICKET_STATUSES = {"open", "in_progress", "blocked", "resolved", "verified"}
_VALID_TICKET_PRIORITIES = {"low", "medium", "high", "urgent"}
_VALID_REVIEW_ACTION_STATUSES = {"new", "reviewed", "ticket_created", "ignored"}
_VALID_SENTIMENT_LABELS = {"positive", "mixed", "negative"}
_VALID_SEVERITY_LABELS = {"low", "medium", "high", "critical"}


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
    if body.priority not in _VALID_TICKET_PRIORITIES:
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


def _create_recurring_issue_ticket(
    *,
    session: Session,
    body: RecurringIssueTicketCreateRequest,
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
        priority=body.priority,
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
    source_type: str | None = Query(default=None),
    source_code: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    include_social_listening: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> OverviewKpiResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if severity is not None and severity not in _VALID_SEVERITY_LABELS:
        raise HTTPException(status_code=422, detail=f"severity must be one of {sorted(_VALID_SEVERITY_LABELS)}")
    if action_status is not None and action_status not in _VALID_REVIEW_ACTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"action_status must be one of {sorted(_VALID_REVIEW_ACTION_STATUSES)}")

    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(selectinload(NormalizedReview.analysis))
    )
    if source_type is not None:
        query = query.where(ReviewSource.source_type == source_type)
    elif not include_social_listening:
        query = query.where(ReviewSource.source_type != "social_listening")
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
    if severity is not None:
        query = query.where(NormalizedReview.severity == severity)
    if action_status is not None:
        query = query.where(NormalizedReview.action_status == action_status)
    if date_from is not None:
        query = query.where(NormalizedReview.review_date >= date_from)
    if date_to is not None:
        query = query.where(NormalizedReview.review_date <= date_to)

    matched_reviews = list(session.scalars(query))
    total = len(matched_reviews)

    sentiment_mix = {label: 0 for label in _VALID_SENTIMENT_LABELS}
    severity_mix = {label: 0 for label in _VALID_SEVERITY_LABELS}
    action_status_mix = {label: 0 for label in _VALID_REVIEW_ACTION_STATUSES}
    department_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    rating_total = 0.0
    rating_count = 0
    severity_score_total = 0
    severity_score_count = 0

    for review in matched_reviews:
        if review.sentiment_label in sentiment_mix:
            sentiment_mix[review.sentiment_label] += 1
        if review.severity in severity_mix:
            severity_mix[review.severity] += 1
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
            severity_score_total += review.analysis.severity_score
            severity_score_count += 1

    average_rating = round(rating_total / rating_count, 2) if rating_count else None
    average_severity_score = round(severity_score_total / severity_score_count) if severity_score_count else 0

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
        average_severity_score=average_severity_score,
        sentiment_mix=sentiment_mix,
        severity_mix=severity_mix,
        action_status_mix=action_status_mix,
        top_departments=top_departments,
        top_categories=top_categories,
        include_social_listening=include_social_listening,
        filters_applied={
            "source_type": source_type,
            "source_code": source_code,
            "issue_category_code": issue_category_code,
            "department_code": department_code,
            "sentiment_label": sentiment_label,
            "severity": severity,
            "action_status": action_status,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    )


@app.get("/issues/summary", tags=["issues"], response_model=IssueSummaryResponse)
async def issues_summary(
    source_type: str | None = Query(default=None),
    source_code: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    include_social_listening: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> IssueSummaryResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if severity is not None and severity not in _VALID_SEVERITY_LABELS:
        raise HTTPException(status_code=422, detail=f"severity must be one of {sorted(_VALID_SEVERITY_LABELS)}")
    if action_status is not None and action_status not in _VALID_REVIEW_ACTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"action_status must be one of {sorted(_VALID_REVIEW_ACTION_STATUSES)}")

    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(
            selectinload(NormalizedReview.source),
            selectinload(NormalizedReview.analysis).selectinload(ReviewAnalysis.issue_category_predictions),
            selectinload(NormalizedReview.issue_category),
        )
    )
    if source_type is not None:
        query = query.where(ReviewSource.source_type == source_type)
    elif not include_social_listening:
        query = query.where(ReviewSource.source_type != "social_listening")
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
    if severity is not None:
        query = query.where(NormalizedReview.severity == severity)
    if action_status is not None:
        query = query.where(NormalizedReview.action_status == action_status)
    if date_from is not None:
        query = query.where(NormalizedReview.review_date >= date_from)
    if date_to is not None:
        query = query.where(NormalizedReview.review_date <= date_to)

    matched_reviews = list(session.scalars(query))
    total = len(matched_reviews)

    # Aggregate per category
    category_aggregates: dict[str, dict] = {}
    for review in matched_reviews:
        cat_code = review.issue_category_code
        if cat_code not in category_aggregates:
            category_aggregates[cat_code] = {
                "category_code": cat_code,
                "category_name": review.issue_category.name if review.issue_category else cat_code.replace("_", " ").title(),
                "review_count": 0,
                "severity_score_total": 0,
                "severity_score_count": 0,
                "primary_department_code": review.department_code,
                "department_counts": {},
                "source_mix": {},
                "min_review_id": review.id,
            }
        agg = category_aggregates[cat_code]
        agg["review_count"] += 1
        if review.analysis is not None:
            agg["severity_score_total"] += review.analysis.severity_score
            agg["severity_score_count"] += 1
        dept = review.department_code
        agg["department_counts"][dept] = agg["department_counts"].get(dept, 0) + 1
        src = review.source_code
        agg["source_mix"][src] = agg["source_mix"].get(src, 0) + 1
        if review.id < agg["min_review_id"]:
            agg["min_review_id"] = review.id

    category_ticket_ids = _ticket_ids_by_source_group(session, "category_recurrence")
    items: list[IssueSummaryItemResponse] = []
    for agg in sorted(category_aggregates.values(), key=lambda x: x["review_count"], reverse=True):
        avg_severity = (
            round(agg["severity_score_total"] / agg["severity_score_count"], 1)
            if agg["severity_score_count"] > 0
            else 0.0
        )
        # Determine primary department from the most frequent department
        primary_dept = max(agg["department_counts"], key=lambda d: agg["department_counts"][d])
        items.append(IssueSummaryItemResponse(
            category_code=agg["category_code"],
            category_name=agg["category_name"],
            review_count=agg["review_count"],
            average_severity_score=avg_severity,
            primary_department_code=primary_dept,
            source_mix=agg["source_mix"],
            representative_review_id=agg["min_review_id"],
            linked_ticket_ids=category_ticket_ids.get(agg["category_code"], []),
        ))

    return IssueSummaryResponse(
        items=items,
        total_reviews=total,
        include_social_listening=include_social_listening,
        filters_applied={
            "source_type": source_type,
            "source_code": source_code,
            "issue_category_code": issue_category_code,
            "department_code": department_code,
            "sentiment_label": sentiment_label,
            "severity": severity,
            "action_status": action_status,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    )


@app.post("/issues/categories/{category_code}/tickets", tags=["tickets"], response_model=TicketResponse, status_code=201)
async def create_category_recurrence_ticket(
    category_code: str,
    body: RecurringIssueTicketCreateRequest,
    source_type: str | None = Query(default=None),
    source_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    sentiment_label: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    include_social_listening: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> ActionTicket:
    category = session.get(IssueCategory, category_code)
    if category is None:
        raise HTTPException(status_code=404, detail="Issue category not found")
    _validate_recurring_ticket_request(body, session)
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if severity is not None and severity not in _VALID_SEVERITY_LABELS:
        raise HTTPException(status_code=422, detail=f"severity must be one of {sorted(_VALID_SEVERITY_LABELS)}")
    if action_status is not None and action_status not in _VALID_REVIEW_ACTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"action_status must be one of {sorted(_VALID_REVIEW_ACTION_STATUSES)}")

    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(selectinload(NormalizedReview.analysis).selectinload(ReviewAnalysis.issue_category_predictions))
        .where(
            NormalizedReview.analysis.has(
                ReviewAnalysis.issue_category_predictions.any(
                    ReviewIssueCategoryPrediction.category_code == category_code
                )
            )
        )
    )
    if source_type is not None:
        query = query.where(ReviewSource.source_type == source_type)
    elif not include_social_listening:
        query = query.where(ReviewSource.source_type != "social_listening")
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)
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
    if severity is not None:
        query = query.where(NormalizedReview.severity == severity)
    if action_status is not None:
        query = query.where(NormalizedReview.action_status == action_status)
    if date_from is not None:
        query = query.where(NormalizedReview.review_date >= date_from)
    if date_to is not None:
        query = query.where(NormalizedReview.review_date <= date_to)

    reviews = list(session.scalars(query.order_by(NormalizedReview.review_date.desc(), NormalizedReview.id)))
    if not reviews:
        raise HTTPException(status_code=404, detail="No reviews found for this issue category recurrence")

    affected_department = body.department_code or _dominant_department(reviews)
    return _create_recurring_issue_ticket(
        session=session,
        body=body,
        department_code=affected_department,
        source_group_type="category_recurrence",
        source_group_key=category_code,
        source_group_label=f"{category.name} recurrence",
        source_category_code=category_code,
        source_cluster_id=None,
        source_review_ids=[review.id for review in reviews],
        note_prefix=f"Created from recurring issue category {category.name}",
    )


@app.post("/analysis/semantic-clusters/{cluster_id}/tickets", tags=["tickets"], response_model=TicketResponse, status_code=201)
async def create_semantic_cluster_ticket(
    cluster_id: str,
    body: RecurringIssueTicketCreateRequest,
    source_type: str | None = Query(default=None),
    source_code: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    department_code: str | None = Query(default=None),
    include_social_listening: bool = Query(default=False),
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
    if source_type is not None:
        query = query.where(ReviewSource.source_type == source_type)
    elif not include_social_listening:
        query = query.where(ReviewSource.source_type != "social_listening")
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
    if body.priority not in _VALID_TICKET_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"priority must be one of {sorted(_VALID_TICKET_PRIORITIES)}")
    if session.scalar(select(Department).where(Department.code == body.department_code)) is None:
        raise HTTPException(status_code=422, detail=f"Unknown department '{body.department_code}'")

    now = datetime.now(timezone.utc)
    ticket = ActionTicket(
        review_id=review_id,
        department_code=body.department_code,
        priority=body.priority,
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
    severity: str | None = Query(default=None),
    issue_category_code: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> TicketsResponse:
    if sentiment_label is not None and sentiment_label not in _VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label must be one of {sorted(_VALID_SENTIMENT_LABELS)}")
    if severity is not None and severity not in _VALID_SEVERITY_LABELS:
        raise HTTPException(status_code=422, detail=f"severity must be one of {sorted(_VALID_SEVERITY_LABELS)}")
    if action_status is not None and action_status not in _VALID_REVIEW_ACTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"action_status must be one of {sorted(_VALID_REVIEW_ACTION_STATUSES)}")

    needs_review_join = any(v is not None for v in [sentiment_label, severity, issue_category_code, action_status])

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
    if severity is not None:
        query = query.where(NormalizedReview.severity == severity)
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

    if body.status is not None and body.status != ticket.status:
        if body.status not in _VALID_TICKET_STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be one of {sorted(_VALID_TICKET_STATUSES)}")
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

    if body.assignee_name is not None or body.assignee_email is not None:
        old_assignee = ticket.assignee_name or ticket.assignee_email
        new_assignee = body.assignee_name or body.assignee_email
        events.append(TicketEvent(ticket_id=ticket_id, event_type="assignment_change", old_value=old_assignee, new_value=new_assignee, occurred_at=now))
        if body.assignee_name is not None:
            ticket.assignee_name = body.assignee_name
        if body.assignee_email is not None:
            ticket.assignee_email = body.assignee_email

    if body.notes is not None:
        events.append(TicketEvent(ticket_id=ticket_id, event_type="note_added", old_value=None, new_value=None, note=body.notes, occurred_at=now))
        ticket.notes = body.notes

    if body.due_date is not None and body.due_date != ticket.due_date:
        events.append(TicketEvent(ticket_id=ticket_id, event_type="due_date_change", old_value=ticket.due_date.isoformat() if ticket.due_date else None, new_value=body.due_date.isoformat(), occurred_at=now))
        ticket.due_date = body.due_date

    if events:
        ticket.updated_at = now
        session.add_all(events)

    session.commit()
    session.refresh(ticket)
    return ticket
