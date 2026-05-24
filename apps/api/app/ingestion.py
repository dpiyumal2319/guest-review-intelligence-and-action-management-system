from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IngestionRun, NormalizedReview, RawReview, ReviewSource
from app.seed_reviews import SEED_REVIEWS


SEED_SOURCE_CODE = "kingsbury_seed_dataset"
SEED_CONNECTOR_KEY = "seed_dataset"


def stable_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_review_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def normalized_values(raw_review_id: int, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
    return {
        "raw_review_id": raw_review_id,
        "source_code": payload["source_code"],
        "external_review_id": payload["external_review_id"],
        "reviewer_name": payload.get("reviewer_name"),
        "review_date": parse_review_date(payload.get("review_date")),
        "rating": payload.get("rating"),
        "language": payload.get("language", "en"),
        "title": payload.get("title"),
        "body": payload["body"],
        "sentiment_label": payload["sentiment_label"],
        "sentiment_score": payload["sentiment_score"],
        "issue_category_code": payload["issue_category_code"],
        "severity": payload["severity"],
        "department_code": payload["department_code"],
        "action_status": "new",
        "normalized_payload": {
            "source_name": payload.get("source_name"),
            "connector_key": SEED_CONNECTOR_KEY,
        },
        "updated_at": now,
    }


def run_seed_ingestion(session: Session) -> IngestionRun:
    now = datetime.now(UTC)
    source = session.get(ReviewSource, SEED_SOURCE_CODE)
    if source is None:
        raise ValueError("Seed source configuration is missing. Run migrations and seed config first.")

    run = IngestionRun(
        connector_key=SEED_CONNECTOR_KEY,
        source_code=SEED_SOURCE_CODE,
        status="running",
        started_at=now,
        records_seen=len(SEED_REVIEWS),
        records_created=0,
        records_updated=0,
        records_skipped=0,
        error_count=0,
        errors=[],
    )
    session.add(run)
    session.flush()

    try:
        for payload in SEED_REVIEWS:
            payload_hash = stable_payload_hash(payload)
            raw_review = session.scalar(
                select(RawReview).where(
                    RawReview.source_code == payload["source_code"],
                    RawReview.external_review_id == payload["external_review_id"],
                )
            )
            payload_changed = True
            if raw_review is None:
                raw_review = RawReview(
                    source_code=payload["source_code"],
                    external_review_id=payload["external_review_id"],
                    ingestion_run_id=run.id,
                    raw_payload=payload,
                    payload_hash=payload_hash,
                    ingested_at=now,
                )
                session.add(raw_review)
                session.flush()
            else:
                payload_changed = raw_review.payload_hash != payload_hash
                raw_review.ingestion_run_id = run.id
                raw_review.raw_payload = payload
                raw_review.payload_hash = payload_hash
                raw_review.ingested_at = now

            values = normalized_values(raw_review.id, payload, now)
            normalized_review = session.scalar(
                select(NormalizedReview).where(
                    NormalizedReview.source_code == payload["source_code"],
                    NormalizedReview.external_review_id == payload["external_review_id"],
                )
            )
            if normalized_review is None:
                session.add(NormalizedReview(**values))
                run.records_created += 1
            elif payload_changed:
                for field, value in values.items():
                    setattr(normalized_review, field, value)
                run.records_updated += 1
            else:
                run.records_skipped += 1

        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:
        session.rollback()
        run = IngestionRun(
            connector_key=SEED_CONNECTOR_KEY,
            source_code=SEED_SOURCE_CODE,
            status="failed",
            started_at=now,
            completed_at=datetime.now(UTC),
            records_seen=len(SEED_REVIEWS),
            error_count=1,
            errors=[str(exc)],
        )
        session.add(run)
        session.commit()

    session.refresh(run)
    return run
