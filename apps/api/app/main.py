from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.registry import CONNECTORS
from app.database import get_session
from app.ingestion import run_mock_connector_by_key, run_seed_ingestion
from app.models import (
    CategoryDepartmentMapping,
    DemoRole,
    Department,
    IngestionRun,
    IssueCategory,
    NormalizedReview,
    ReviewSource,
    SeverityThreshold,
)
from app.schemas import (
    HealthResponse,
    IngestionRunResponse,
    IngestionRunsResponse,
    IngestionSourceStatusesResponse,
    ReferenceConfigResponse,
    ReviewsResponse,
)


app = FastAPI(
    title="Guest Review Intelligence API",
    summary="REST API for the hotel review intelligence prototype.",
    version="0.1.0",
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
async def reviews(session: Session = Depends(get_session)) -> ReviewsResponse:
    imported_reviews = list(session.scalars(select(NormalizedReview).order_by(NormalizedReview.review_date.desc())))
    return ReviewsResponse(reviews=imported_reviews)
