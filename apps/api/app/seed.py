from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    DemoRole,
    Department,
    ReviewSource,
)
from app.seed_data import (
    DEMO_ROLES,
    DEPARTMENTS,
    REVIEW_SOURCES,
)


def upsert_rows(session: Session, model: type, rows: Iterable[dict[str, Any]]) -> None:
    for row in rows:
        session.merge(model(**row))


def seed_reference_config(session: Session) -> None:
    upsert_rows(session, ReviewSource, REVIEW_SOURCES)
    upsert_rows(session, Department, DEPARTMENTS)
    upsert_rows(session, DemoRole, DEMO_ROLES)
    session.commit()


def main() -> None:
    with SessionLocal() as session:
        seed_reference_config(session)


if __name__ == "__main__":
    main()
