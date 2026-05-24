from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import (
    CategoryDepartmentMapping,
    DemoRole,
    Department,
    IssueCategory,
    ReviewSource,
    SeverityThreshold,
)
from app.schemas import HealthResponse, ReferenceConfigResponse


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
