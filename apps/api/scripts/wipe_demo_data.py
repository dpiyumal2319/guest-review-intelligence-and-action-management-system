from __future__ import annotations

from sqlalchemy import text

from app.database import SessionLocal


DEMO_TABLES = (
    "ticket_events",
    "action_tickets",
    "review_issue_category_predictions",
    "review_analyses",
    "normalized_reviews",
    "raw_reviews",
    "ingestion_runs",
)


def main() -> None:
    with SessionLocal() as session:
        session.execute(text(f"TRUNCATE {', '.join(DEMO_TABLES)} RESTART IDENTITY CASCADE"))
        session.commit()
    print("wiped demo review, analysis, ticket, and ingestion data; reference config preserved")


if __name__ == "__main__":
    main()
