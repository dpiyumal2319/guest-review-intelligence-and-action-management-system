"""Dry-run the issue extraction + consolidation passes on a small subset of reviews.

Use this to tune prompts cheaply before a full detection run. It reads reviews already in the
DB (no re-ingestion needed), runs Pass A (extract) and Pass B (consolidate) only, and prints
the resulting canonical issues with their member labels and a sample description. It does NOT
write anything to the database.

Examples:
    python scripts/test_issue_subset.py --limit 40
    python scripts/test_issue_subset.py --topic "air condition" --limit 30
    python scripts/test_issue_subset.py --ids 12,15,20
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import NormalizedReview, ReviewAnalysis  # noqa: E402
from app.llm_client import get_llm_client  # noqa: E402
from app import issue_detection as D  # noqa: E402


def _select_reviews(session, *, limit: int, topic: str | None, ids: list[int] | None):
    if ids:
        rows = session.scalars(select(NormalizedReview).where(NormalizedReview.id.in_(ids)))
        return list(rows)
    query = (
        select(NormalizedReview)
        .where(NormalizedReview.analysis.has(ReviewAnalysis.sentiment_label.in_(["negative", "mixed"])))
        .order_by(NormalizedReview.review_date.desc(), NormalizedReview.id.desc())
    )
    reviews = list(session.scalars(query))
    if topic:
        needle = topic.lower()
        reviews = [r for r in reviews if needle in (r.body or "").lower()]
    return reviews[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--topic", default=None, help="Only reviews whose body contains this substring.")
    parser.add_argument("--ids", default=None, help="Comma-separated review ids.")
    args = parser.parse_args()

    client = get_llm_client()
    if not client.is_available():
        print("ERROR: No LLM provider configured. Set GEMINI_API_KEY or LLM_PROVIDER=stub.")
        return 1
    print(f"LLM provider: {client.provider_name} ({client.model_name})\n")

    ids = [int(x) for x in args.ids.split(",")] if args.ids else None

    session = SessionLocal()
    try:
        reviews = _select_reviews(session, limit=args.limit, topic=args.topic, ids=ids)
        if not reviews:
            print("No matching reviews found.")
            return 0
        print(f"Selected {len(reviews)} review(s).\n")

        mentions = D._extract_problems(client, reviews)
        print(f"Pass A extracted {len(mentions)} problem mention(s).")

        summary_to_canonical = D._consolidate_problems(client, mentions)
        review_by_id = {r.id: r for r in reviews}

        groups: dict[tuple[str, str], list[int]] = {}
        for m in mentions:
            dept, title = summary_to_canonical.get(
                m["summary"].strip().lower(),
                (D._normalize_department(m["department_code"]), m["summary"][:200]),
            )
            groups.setdefault((dept, title), []).append(m["review_id"])

        print(f"Pass B consolidated into {len(groups)} canonical issue(s):\n")
        for (dept, title), rids in sorted(groups.items(), key=lambda kv: -len(set(kv[1]))):
            unique_rids = sorted(set(rids))
            evidence = [
                (review_by_id[rid].body or "")[:120]
                for rid in unique_rids
                if rid in review_by_id
            ][:6]
            description = D._describe_issue(client, title, evidence, len(unique_rids))
            status = "active" if len(unique_rids) >= D.MIN_EVIDENCE_FOR_PROMOTION else "emerging"
            print(f"  [{dept}] {title}  ({len(unique_rids)} reviews, {status})")
            if description:
                print(f"     ↳ {description}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
