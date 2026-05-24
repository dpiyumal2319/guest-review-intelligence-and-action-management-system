from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import MockConnector
from app.connectors.registry import get_connector
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


def normalized_values(raw_review_id: int, payload: dict[str, Any], now: datetime, connector_key: str) -> dict[str, Any]:
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
            "connector_key": connector_key,
            "source_type": payload.get("source_type"),
            "source_url": payload.get("source_url"),
        },
        "updated_at": now,
    }


def canonical_review_values(raw_review_id: int, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
    normalized_payload = {
        "source_name": payload.get("source_name"),
        "connector_key": SEED_CONNECTOR_KEY,
    }
    normalized_payload.update(payload.get("normalized_payload", {}))
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
        "normalized_payload": normalized_payload,
        "updated_at": now,
    }


def upsert_ingested_review(
    session: Session,
    run: IngestionRun,
    raw_payload: dict[str, Any],
    normalized_payload: dict[str, Any],
    now: datetime,
) -> None:
    payload_hash = stable_payload_hash(raw_payload)
    raw_review = session.scalar(
        select(RawReview).where(
            RawReview.source_code == normalized_payload["source_code"],
            RawReview.external_review_id == normalized_payload["external_review_id"],
        )
    )
    payload_changed = True
    if raw_review is None:
        raw_review = RawReview(
            source_code=normalized_payload["source_code"],
            external_review_id=normalized_payload["external_review_id"],
            ingestion_run_id=run.id,
            raw_payload=raw_payload,
            payload_hash=payload_hash,
            ingested_at=now,
        )
        session.add(raw_review)
        session.flush()
    else:
        payload_changed = raw_review.payload_hash != payload_hash
        raw_review.ingestion_run_id = run.id
        raw_review.raw_payload = raw_payload
        raw_review.payload_hash = payload_hash
        raw_review.ingested_at = now

    values = canonical_review_values(raw_review.id, normalized_payload, now)
    normalized_review = session.scalar(
        select(NormalizedReview).where(
            NormalizedReview.source_code == normalized_payload["source_code"],
            NormalizedReview.external_review_id == normalized_payload["external_review_id"],
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


def run_mock_connector(session: Session, connector: MockConnector) -> IngestionRun:
    now = datetime.now(UTC)
    source = session.get(ReviewSource, connector.source_code)
    if source is None:
        raise ValueError(f"Review source configuration is missing for {connector.source_code}.")
    if not source.is_verified_channel or source.source_type != "verified_review":
        raise ValueError(f"Connector {connector.connector_key} is not configured as a verified review source.")

    records = list(connector.iter_records())
    run = IngestionRun(
        connector_key=connector.connector_key,
        source_code=connector.source_code,
        status="running",
        started_at=now,
        records_seen=len(records),
        records_created=0,
        records_updated=0,
        records_skipped=0,
        error_count=0,
        errors=[],
    )
    session.add(run)
    session.flush()

    try:
        for raw_payload in records:
            normalized_payload = connector.normalize(raw_payload)
            upsert_ingested_review(session, run, raw_payload, normalized_payload, now)

        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:
        session.rollback()
        run = IngestionRun(
            connector_key=connector.connector_key,
            source_code=connector.source_code,
            status="failed",
            started_at=now,
            completed_at=datetime.now(UTC),
            records_seen=len(records),
            error_count=1,
            errors=[str(exc)],
        )
        session.add(run)
        session.commit()

    session.refresh(run)
    return run


def run_mock_connector_by_key(session: Session, connector_key: str) -> IngestionRun:
    return run_mock_connector(session, get_connector(connector_key))


def run_payload_ingestion(
    session: Session,
    *,
    source_code: str,
    connector_key: str,
    payloads: list[dict[str, Any]],
) -> IngestionRun:
    now = datetime.now(UTC)
    source = session.get(ReviewSource, source_code)
    if source is None:
        raise ValueError(f"{source_code} source configuration is missing. Run migrations and seed config first.")

    run = IngestionRun(
        connector_key=connector_key,
        source_code=source_code,
        status="running",
        started_at=now,
        records_seen=len(payloads),
        records_created=0,
        records_updated=0,
        records_skipped=0,
        error_count=0,
        errors=[],
    )
    session.add(run)
    session.flush()

    try:
        for payload in payloads:
            if payload["source_code"] != source_code:
                raise ValueError(
                    f"Payload {payload['external_review_id']} belongs to {payload['source_code']}, not {source_code}."
                )
            payload_with_metadata = {
                **payload,
                "normalized_payload": {
                    **payload.get("normalized_payload", {}),
                    "source_type": payload.get("source_type"),
                    "source_url": payload.get("source_url"),
                    "connector_key": connector_key,
                },
            }
            upsert_ingested_review(session, run, payload, payload_with_metadata, now)

        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:
        session.rollback()
        run = IngestionRun(
            connector_key=connector_key,
            source_code=source_code,
            status="failed",
            started_at=now,
            completed_at=datetime.now(UTC),
            records_seen=len(payloads),
            error_count=1,
            errors=[str(exc)],
        )
        session.add(run)
        session.commit()

    session.refresh(run)
    return run


def run_seed_ingestion(session: Session) -> IngestionRun:
    return run_payload_ingestion(
        session,
        source_code=SEED_SOURCE_CODE,
        connector_key=SEED_CONNECTOR_KEY,
        payloads=SEED_REVIEWS,
    )
