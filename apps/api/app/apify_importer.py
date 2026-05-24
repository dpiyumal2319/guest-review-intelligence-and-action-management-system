from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import io
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.ingestion import (
    count_duplicate_flagged_for_run,
    parse_review_date,
    stable_payload_hash,
    upsert_ingested_review,
)
from app.models import IngestionRun, ReviewSource


APIFY_SOURCE_CODE = "apify_dataset_import"
APIFY_CONNECTOR_KEY = "apify_dataset_import"

SUPPORTED_EXTENSIONS = {".json", ".csv"}
ITEM_KEYS = ("items", "results", "data", "reviews")
BODY_KEYS = ("body", "text", "reviewText", "review_text", "textTranslated", "comment", "content", "review")
TITLE_KEYS = ("title", "reviewTitle", "review_title", "headline")
RATING_KEYS = ("rating", "stars", "score", "reviewRating")
DATE_KEYS = ("review_date", "date", "publishedAt", "published_at", "createdAt", "reviewDate", "timestamp")
REVIEWER_KEYS = ("reviewer_name", "reviewerName", "userName", "username", "name", "author")
ID_KEYS = ("external_review_id", "reviewId", "review_id", "id", "uuid")
SOURCE_URL_KEYS = ("source_url", "sourceUrl", "reviewUrl", "url", "pageUrl", "placeUrl")
PLATFORM_KEYS = ("platform", "source", "site", "provider")
ACTOR_KEYS = ("actor_name", "actorName", "actor", "apifyActor")
EXPORT_DATE_KEYS = ("export_date", "exportDate", "exportedAt", "datasetExportDate")


@dataclass(frozen=True)
class ApifyImportInput:
    file_path: str | None = None
    content: str | None = None
    file_name: str | None = None
    actor_name: str | None = None
    export_date: str | None = None
    platform: str | None = None
    source_url: str | None = None


def run_apify_dataset_import(session: Session, import_input: ApifyImportInput) -> IngestionRun:
    now = datetime.now(UTC)
    source = session.get(ReviewSource, APIFY_SOURCE_CODE)
    if source is None:
        raise ValueError("Apify dataset source configuration is missing. Run migrations and seed config first.")

    run = IngestionRun(
        connector_key=APIFY_CONNECTOR_KEY,
        source_code=APIFY_SOURCE_CODE,
        status="running",
        started_at=now,
        records_seen=0,
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
        rows, dataset_metadata = load_apify_rows(import_input)
        dataset_metadata = merge_dataset_metadata(dataset_metadata, import_input)
        run.records_seen = len(rows)

        for row_number, row in enumerate(rows, start=1):
            try:
                payload = normalize_apify_row(row, row_number, dataset_metadata)
            except ValueError as exc:
                run.error_count += 1
                run.errors = [*run.errors, f"row {row_number}: {exc}"]
                continue

            raw_payload = {
                "dataset_metadata": dataset_metadata,
                "record": row,
            }
            upsert_ingested_review(session, run, raw_payload, payload, now)

        run.records_duplicate_flagged = count_duplicate_flagged_for_run(session, run)
        run.status = "completed_with_errors" if run.error_count else "completed"
        run.completed_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:
        session.rollback()
        run = IngestionRun(
            connector_key=APIFY_CONNECTOR_KEY,
            source_code=APIFY_SOURCE_CODE,
            status="failed",
            started_at=now,
            completed_at=datetime.now(UTC),
            error_count=1,
            errors=[str(exc)],
        )
        session.add(run)
        session.commit()

    session.refresh(run)
    return run


def load_apify_rows(import_input: ApifyImportInput) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    content, format_hint, file_label = read_import_content(import_input)
    if format_hint == ".json" or content.lstrip().startswith(("[", "{")):
        return load_json_rows(content, file_label)
    if format_hint == ".csv":
        return load_csv_rows(content, file_label), {"file_name": file_label}
    raise ValueError("Unsupported Apify import input. Provide a .json or .csv export.")


def read_import_content(import_input: ApifyImportInput) -> tuple[str, str | None, str | None]:
    if import_input.content is not None:
        file_label = import_input.file_name
        return import_input.content, suffix_for(file_label), file_label
    if import_input.file_path is None:
        raise ValueError("Provide either file_path or content for the Apify offline import.")

    path = Path(import_input.file_path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported Apify import file type. Use a JSON or CSV export.")
    if not path.is_file():
        raise ValueError(f"Apify import file not found: {path}")
    return path.read_text(encoding="utf-8-sig"), path.suffix.lower(), path.name


def load_json_rows(content: str, file_label: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import json

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON export: {exc.msg}") from exc

    metadata: dict[str, Any] = {"file_name": file_label}
    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, dict):
        metadata.update(extract_metadata(parsed))
        rows = next((parsed[key] for key in ITEM_KEYS if isinstance(parsed.get(key), list)), None)
        if rows is None:
            rows = [parsed]
    else:
        raise ValueError("Unsupported JSON export shape. Expected an object or array.")

    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Unsupported JSON export shape. Dataset rows must be objects.")
    return list(rows), compact_metadata(metadata)


def load_csv_rows(content: str, file_label: str | None) -> list[dict[str, Any]]:
    rows = list(csv.DictReader(io.StringIO(content)))
    if not rows:
        raise ValueError("CSV export has no rows.")
    if not rows[0]:
        raise ValueError("CSV export must include a header row.")
    return rows


def normalize_apify_row(row: dict[str, Any], row_number: int, dataset_metadata: dict[str, Any]) -> dict[str, Any]:
    body = first_text(row, BODY_KEYS)
    if body is None:
        raise ValueError("missing review text")

    rating = parse_rating(first_present(row, RATING_KEYS))
    review_date = parse_optional_date(first_text(row, DATE_KEYS))
    platform = first_text(row, PLATFORM_KEYS) or dataset_metadata.get("platform")
    source_url = first_text(row, SOURCE_URL_KEYS) or dataset_metadata.get("source_url")
    external_review_id = first_text(row, ID_KEYS)
    if external_review_id is None:
        external_review_id = generated_external_id(row, body, review_date, source_url, row_number)

    sentiment_label, sentiment_score = sentiment_from_rating(rating)
    issue_category_code, severity, department_code = defaults_from_rating(rating, sentiment_label)

    row_metadata = compact_metadata(
        {
            "actor_name": first_text(row, ACTOR_KEYS),
            "export_date": first_text(row, EXPORT_DATE_KEYS),
            "platform": platform,
            "source_url": source_url,
        }
    )

    return {
        "source_code": APIFY_SOURCE_CODE,
        "external_review_id": external_review_id,
        "reviewer_name": first_text(row, REVIEWER_KEYS),
        "review_date": review_date,
        "rating": rating,
        "language": first_text(row, ("language", "lang")) or "en",
        "title": first_text(row, TITLE_KEYS),
        "body": body,
        "sentiment_label": sentiment_label,
        "sentiment_score": sentiment_score,
        "issue_category_code": issue_category_code,
        "severity": severity,
        "department_code": department_code,
        "dataset_metadata": compact_metadata(dataset_metadata | row_metadata),
        "normalized_payload": {
            "source_kind": "dataset_import",
            "connector_key": APIFY_CONNECTOR_KEY,
            "dataset_metadata": compact_metadata(dataset_metadata | row_metadata),
            "normalization_note": "Offline Apify dataset preparation import; not a production connector.",
        },
    }


def merge_dataset_metadata(metadata: dict[str, Any], import_input: ApifyImportInput) -> dict[str, Any]:
    return compact_metadata(
        metadata
        | compact_metadata({
            "actor_name": import_input.actor_name,
            "export_date": import_input.export_date,
            "platform": import_input.platform,
            "source_url": import_input.source_url,
            "file_name": import_input.file_name or metadata.get("file_name"),
        })
    )


def extract_metadata(parsed: dict[str, Any]) -> dict[str, Any]:
    metadata = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    return compact_metadata(
        metadata
        | {
            "actor_name": first_text(parsed, ACTOR_KEYS),
            "export_date": first_text(parsed, EXPORT_DATE_KEYS),
            "platform": first_text(parsed, PLATFORM_KEYS),
            "source_url": first_text(parsed, SOURCE_URL_KEYS),
            "dataset_id": first_text(parsed, ("datasetId", "dataset_id")),
        }
    )


def first_present(row: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value = first_present(row, keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_rating(value: Any | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        rating = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid rating {value!r}") from exc
    if rating < 0 or rating > 5:
        raise ValueError(f"rating out of expected 0-5 range: {rating}")
    return rating


def parse_optional_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return parse_review_date(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid review date {value!r}") from exc


def sentiment_from_rating(rating: float | None) -> tuple[str, float]:
    if rating is None:
        return "mixed", 0.0
    if rating >= 4:
        return "positive", 0.65
    if rating <= 2:
        return "negative", -0.65
    return "mixed", -0.05


def defaults_from_rating(rating: float | None, sentiment_label: str) -> tuple[str, str, str]:
    if sentiment_label == "positive":
        return "positive_general", "low", "guest_relations"
    if rating is not None and rating <= 2:
        return "other_uncategorized", "high", "guest_relations"
    return "other_uncategorized", "medium", "guest_relations"


def generated_external_id(
    row: dict[str, Any],
    body: str,
    review_date: datetime | None,
    source_url: str | None,
    row_number: int,
) -> str:
    identity_payload = {
        "body": body,
        "review_date": review_date.isoformat() if review_date else None,
        "rating": first_present(row, RATING_KEYS),
        "reviewer_name": first_text(row, REVIEWER_KEYS),
        "source_url": source_url,
        "row_number": row_number,
    }
    return f"apify-{stable_payload_hash(identity_payload)[:24]}"


def suffix_for(file_name: str | None) -> str | None:
    if file_name is None:
        return None
    return Path(file_name).suffix.lower()


def compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if value not in (None, "")}
