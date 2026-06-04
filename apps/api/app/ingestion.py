from datetime import UTC, datetime
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import unicodedata
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis import analyze_and_persist_review
from app.connectors.base import MockConnector
from app.connectors.registry import get_connector
from app.models import IngestionRun, NormalizedReview, RawReview, ReviewSource
from app.seed_reviews import SEED_REVIEWS


SEED_SOURCE_CODE = "google_business_profile"
SEED_CONNECTOR_KEY = "google_business_profile"
PENDING_ANALYSIS_VALUES = {
    "sentiment_label": "pending",
    "sentiment_score": 0.0,
    "issue_category_code": "other_uncategorized",
    "reputation_risk": "low",
    "department_code": "guest_relations",
}


def stable_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_text(value: Any | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    compacted = " ".join(text.split())
    return compacted or None


def canonical_rating(value: Any | None) -> str | None:
    if value is None:
        return None
    rating = Decimal(str(value)).normalize()
    return format(rating, "f")


def normalized_content_hash(payload: dict[str, Any]) -> str:
    canonical_payload = {
        "body": canonical_text(payload.get("body")),
        "language": canonical_text(payload.get("language", "en")),
        "rating": canonical_rating(payload.get("rating")),
        "title": canonical_text(payload.get("title")),
    }
    return stable_payload_hash(canonical_payload)


def parse_review_date(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


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
        "content_hash": normalized_content_hash(payload),
        "sentiment_label": payload.get("sentiment_label", PENDING_ANALYSIS_VALUES["sentiment_label"]),
        "sentiment_score": payload.get("sentiment_score", PENDING_ANALYSIS_VALUES["sentiment_score"]),
        "issue_category_code": payload.get("issue_category_code", PENDING_ANALYSIS_VALUES["issue_category_code"]),
        "reputation_risk": payload.get("reputation_risk", PENDING_ANALYSIS_VALUES["reputation_risk"]),
        "department_code": payload.get("department_code", PENDING_ANALYSIS_VALUES["department_code"]),
        "action_status": "new",
        "normalized_payload": normalized_payload,
        "updated_at": now,
    }


def load_connector_fixture_records(connector: MockConnector, fixture_path: str | Path | None) -> list[dict[str, Any]]:
    if fixture_path is None:
        return list(connector.iter_records())

    resolved_path = Path(fixture_path).expanduser().resolve()
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"Fixture file {resolved_path} must contain a JSON array of objects.")
    return list(payload)


def refresh_content_duplicate_group(session: Session, content_hash: str) -> None:
    if not content_hash:
        return
    reviews = list(
        session.scalars(
            select(NormalizedReview)
            .where(NormalizedReview.content_hash == content_hash)
            .order_by(NormalizedReview.id)
        )
    )
    if len(reviews) <= 1:
        for review in reviews:
            review.is_content_duplicate = False
            review.duplicate_of_review_id = None
        return

    canonical_review = reviews[0]
    for review in reviews:
        review.is_content_duplicate = True
        review.duplicate_of_review_id = None if review.id == canonical_review.id else canonical_review.id


def count_duplicate_flagged_for_run(session: Session, run: IngestionRun) -> int:
    return (
        session.scalar(
            select(func.count(NormalizedReview.id))
            .join(RawReview, NormalizedReview.raw_review_id == RawReview.id)
            .where(
                RawReview.ingestion_run_id == run.id,
                NormalizedReview.is_content_duplicate.is_(True),
            )
        )
        or 0
    )


def upsert_ingested_review(
    session: Session,
    run: IngestionRun,
    raw_payload: dict[str, Any],
    normalized_payload: dict[str, Any],
    now: datetime,
) -> None:
    payload_hash = stable_payload_hash(raw_payload)
    previous_content_hash: str | None = None
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
        normalized_review = NormalizedReview(**values)
        session.add(normalized_review)
        session.flush()
        analyze_and_persist_review(session, normalized_review, now)
        run.records_created += 1
    elif payload_changed:
        previous_content_hash = normalized_review.content_hash
        for field, value in values.items():
            setattr(normalized_review, field, value)
        analyze_and_persist_review(session, normalized_review, now)
        run.records_updated += 1
    else:
        if normalized_review.content_hash != values["content_hash"]:
            previous_content_hash = normalized_review.content_hash
            normalized_review.content_hash = values["content_hash"]
        run.records_skipped += 1

    if previous_content_hash and previous_content_hash != values["content_hash"]:
        refresh_content_duplicate_group(session, previous_content_hash)
    refresh_content_duplicate_group(session, values["content_hash"])


def run_mock_connector(
    session: Session,
    connector: MockConnector,
    *,
    fixture_path: str | Path | None = None,
) -> IngestionRun:
    now = datetime.now(UTC)
    source = session.get(ReviewSource, connector.source_code)
    if source is None:
        raise ValueError(f"Review source configuration is missing for {connector.source_code}.")
    if not source.is_verified_channel:
        raise ValueError(f"Connector {connector.connector_key} is not configured as a verified review source.")

    records = load_connector_fixture_records(connector, fixture_path)
    run = IngestionRun(
        connector_key=connector.connector_key,
        source_code=connector.source_code,
        status="running",
        started_at=now,
        records_seen=len(records),
        records_created=0,
        records_updated=0,
        records_skipped=0,
        records_duplicate_flagged=0,
        error_count=0,
        errors=[],
    )
    session.add(run)
    session.flush()

    try:
        for raw_payload in records:
            normalized_payload = connector.normalize(raw_payload)
            upsert_ingested_review(session, run, raw_payload, normalized_payload, now)

        run.records_duplicate_flagged = count_duplicate_flagged_for_run(session, run)
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


def run_mock_connector_by_key(
    session: Session,
    connector_key: str,
    fixture_path: str | Path | None = None,
) -> IngestionRun:
    return run_mock_connector(session, get_connector(connector_key), fixture_path=fixture_path)


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
        records_duplicate_flagged=0,
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
                    "source_url": payload.get("source_url"),
                    "connector_key": connector_key,
                },
            }
            upsert_ingested_review(session, run, payload, payload_with_metadata, now)

        run.records_duplicate_flagged = count_duplicate_flagged_for_run(session, run)
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
    platform_seed_reviews = [
        {
            **review,
            "source_code": SEED_SOURCE_CODE,
            "external_review_id": review["external_review_id"].replace("seed-kg", "gbp-seed", 1),
        }
        for review in SEED_REVIEWS
    ]
    return run_payload_ingestion(
        session,
        source_code=SEED_SOURCE_CODE,
        connector_key=SEED_CONNECTOR_KEY,
        payloads=platform_seed_reviews,
    )
