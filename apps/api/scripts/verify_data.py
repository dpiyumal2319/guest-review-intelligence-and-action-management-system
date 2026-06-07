"""Verify demo data: review counts, issues, and evidence links."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from sqlalchemy import func, select, text
from app.models import DetectedIssue, IssueReviewLink, NormalizedReview


def main() -> None:
    with SessionLocal() as session:
        counts = session.execute(
            text("SELECT source_code, count(*) FROM normalized_reviews GROUP BY source_code ORDER BY source_code")
        ).all()
        print("=== Reviews by source ===")
        for row in counts:
            print(f"  {row[0]}: {row[1]}")

        issues = session.execute(
            text("SELECT department_code, status, count(*) FROM detected_issues GROUP BY department_code, status ORDER BY department_code, status")
        ).all()
        print("\n=== Issues by department/status ===")
        for row in issues:
            print(f"  {row[0]} ({row[1]}): {row[2]}")

        links = session.scalar(select(func.count(IssueReviewLink.id))) or 0
        print(f"\n=== Evidence links: {links} ===")


if __name__ == "__main__":
    main()
