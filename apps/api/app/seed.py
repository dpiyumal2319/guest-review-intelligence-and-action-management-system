from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    CategoryDepartmentMapping,
    DemoRole,
    Department,
    IssueCategory,
    ReviewSource,
    SeverityThreshold,
)
from app.seed_data import (
    CATEGORY_DEPARTMENT_MAPPINGS,
    DEMO_ROLES,
    DEPARTMENTS,
    ISSUE_CATEGORIES,
    REVIEW_SOURCES,
    SEVERITY_THRESHOLDS,
)


def upsert_rows(session: Session, model: type, rows: Iterable[dict[str, Any]]) -> None:
    for row in rows:
        session.merge(model(**row))


def seed_reference_config(session: Session) -> None:
    upsert_rows(session, ReviewSource, REVIEW_SOURCES)
    upsert_rows(session, Department, DEPARTMENTS)
    upsert_rows(session, IssueCategory, ISSUE_CATEGORIES)
    upsert_rows(session, CategoryDepartmentMapping, CATEGORY_DEPARTMENT_MAPPINGS)
    upsert_rows(session, SeverityThreshold, SEVERITY_THRESHOLDS)
    upsert_rows(session, DemoRole, DEMO_ROLES)
    session.commit()


def main() -> None:
    with SessionLocal() as session:
        seed_reference_config(session)


if __name__ == "__main__":
    main()
