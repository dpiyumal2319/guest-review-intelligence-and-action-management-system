"""Transform crawled real reviews into connector-native fixtures.

Two real datasets live in ``apps/api/data/real-reviews/``:

* ``dataset_crawler-google-places_*.json`` -- Google Places crawl. Many records are
  owner-reply-only (no review text); those are dropped. The file is cleaned **in place**
  (originals are not needed). All remaining text reviews -- positive and negative -- are kept;
  positives never reach Gemini because issue detection only feeds negative/mixed reviews to it.
* ``dataset_tripadvisor-reviews_*.json`` -- TripAdvisor crawl, already filtered to 1-3 star.

The crawler shapes are mapped onto the shapes the existing connectors expect
(``normalize_google_business_profile`` / ``normalize_tripadvisor``) and written to
``apps/api/data/real-reviews/connectors/``. Review dates are re-stamped into the newest window
(2026-06-06 .. today) so the real reviews surface at the top of detection's candidate cap and the
dashboards -- highlighting them without any new UI or subsystem.

Deterministic: stable external IDs and a fixed date window, so re-runs are idempotent.

Usage::

    .venv/bin/python scripts/transform_real_reviews.py
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import glob
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REAL_DIR = ROOT / "data" / "real-reviews"
CONNECTORS_DIR = REAL_DIR / "connectors"

# Newest window: just above the synthetic fixtures' max (2026-06-05) up to "today".
WINDOW_START = datetime(2026, 6, 6, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 6, 9, 23, 59, 59, tzinfo=UTC)

STAR_WORDS = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE"}
TA_LOCATION_ID = "the-kingsbury-colombo-demo"

# Only low Google Places reviews drive Issues. The 4-5 star positives only add dashboard
# sentiment bulk -- which the synthetic fixtures already provide -- but each one still costs a
# full local-ML ingestion pass (~6s on a 6GB GPU). Ingest only <= this many stars; the raw file
# is still cleaned in place with all text reviews for reference. (TripAdvisor is already 1-3 star.)
GP_FIXTURE_MAX_STARS = 3

# Treat these as English-safe to keep ML/Gemini input clean.
ENGLISH_LANGS = {"en", "en-US", "en-GB", None, ""}


def _glob_one(pattern: str) -> Path:
    matches = sorted(glob.glob(str(REAL_DIR / pattern)))
    if not matches:
        raise FileNotFoundError(f"No file matching {pattern!r} in {REAL_DIR}")
    return Path(matches[-1])


def iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def clamp(value: datetime) -> datetime:
    return min(value, WINDOW_END)


def gp_english_text(rec: dict[str, Any]) -> str | None:
    """Best English text for a Google Places record, or None if unusable."""
    translated = (rec.get("textTranslated") or "").strip()
    if translated:
        return translated
    original = (rec.get("text") or "").strip()
    if original and rec.get("originalLanguage") in ENGLISH_LANGS:
        return original
    return None


def gp_stars(rec: dict[str, Any]) -> int | None:
    value = rec.get("stars")
    if value is None:
        value = rec.get("rating")
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        return None
    return ivalue if ivalue in STAR_WORDS else None


def clean_google_places(raw_path: Path) -> list[dict[str, Any]]:
    """Drop reply-only / non-English records; rewrite the GP file in place."""
    records = json.loads(raw_path.read_text(encoding="utf-8"))
    kept: list[dict[str, Any]] = []
    for rec in records:
        if gp_english_text(rec) is None or gp_stars(rec) is None or not rec.get("reviewId"):
            continue
        kept.append(rec)
    raw_path.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    return kept


def ta_external_id(url: str, fallback_index: int) -> str:
    match = re.search(r"-r(\d+)-", url or "")
    if match:
        return f"tripadvisor-{match.group(1)}"
    return f"tripadvisor-real-{fallback_index:06d}"


def parse_dt(value: Any) -> datetime:
    """Parse a crawler date; fall back to the window start. Used only for relative ordering."""
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return WINDOW_START
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    return WINDOW_START


def restamp_dates(total: int) -> list[datetime]:
    """Evenly spaced datetimes across the window, newest first (index 0 = newest)."""
    if total <= 0:
        return []
    if total == 1:
        return [WINDOW_END]
    span = (WINDOW_END - WINDOW_START).total_seconds()
    return [
        WINDOW_END - timedelta(seconds=span * (i / (total - 1)))
        for i in range(total)
    ]


def build_gp_fixture(records: list[dict[str, Any]], created_by_id: dict[str, datetime]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in records:
        created = created_by_id[rec["reviewId"]]
        text = gp_english_text(rec)
        payload: dict[str, Any] = {
            "name": f"accounts/real/locations/kingsbury/reviews/{rec['reviewId']}",
            "reviewId": rec["reviewId"],
            "reviewer": {"displayName": rec.get("name") or "Google user", "isAnonymous": False},
            "starRating": STAR_WORDS[gp_stars(rec)],
            "comment": text,
            "createTime": iso_z(created),
            "updateTime": iso_z(clamp(created + timedelta(hours=6))),
        }
        reply = (rec.get("responseFromOwnerText") or "").strip()
        if reply:
            payload["reviewReply"] = {
                "comment": reply,
                "updateTime": iso_z(clamp(created + timedelta(days=1))),
            }
        out.append(payload)
    return out


def build_ta_fixture(records: list[dict[str, Any]], created_by_id: dict[str, datetime]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, rec in enumerate(records):
        ext_id = ta_external_id(rec.get("url", ""), index)
        created = created_by_id[ext_id]
        user = rec.get("user") or {}
        contributions = (user.get("contributions") or {}).get("totalContributions", 0)
        payload: dict[str, Any] = {
            "id": ext_id,
            "location_id": TA_LOCATION_ID,
            "url": rec.get("url", ""),
            "rating": int(rec["rating"]),
            "published_date": created.isoformat(),
            "travel_date": created.strftime("%Y-%m"),
            "title": rec.get("title"),
            "text": (rec.get("text") or "").strip(),
            "user": {
                "username": user.get("username") or user.get("name") or "TripAdvisor user",
                "user_location": {"name": (user.get("userLocation") or {}).get("name")},
                "contributions": contributions,
            },
        }
        owner = (rec.get("ownerResponse") or {})
        owner_text = (owner.get("text") or "").strip() if isinstance(owner, dict) else ""
        if owner_text:
            payload["management_response"] = {
                "text": owner_text,
                "published_date": clamp(created + timedelta(days=1)).isoformat(),
            }
        out.append(payload)
    return out


def main() -> None:
    gp_path = _glob_one("dataset_crawler-google-places_*.json")
    ta_path = _glob_one("dataset_tripadvisor-reviews_*.json")

    gp_all = clean_google_places(gp_path)  # cleaned in place: all English text reviews
    # Ingest only low-star GP reviews (positives add only dashboard bulk at full ML cost).
    gp_records = [r for r in gp_all if (gp_stars(r) or 5) <= GP_FIXTURE_MAX_STARS]
    ta_records = [r for r in json.loads(ta_path.read_text(encoding="utf-8")) if (r.get("text") or "").strip()]

    # Build a combined newest-first ordering across both platforms (by original crawl date),
    # then assign re-stamped dates so every real review lands above the synthetic window.
    combined: list[tuple[str, str]] = []  # (kind, external_id)
    gp_dates_src = {r["reviewId"]: parse_dt(r.get("publishedAtDate")) for r in gp_records}
    ta_ids = [ta_external_id(r.get("url", ""), i) for i, r in enumerate(ta_records)]
    ta_dates_src = {
        ta_ids[i]: parse_dt(r.get("publishedDate")) for i, r in enumerate(ta_records)
    }
    for rid in gp_dates_src:
        combined.append(("gp", rid))
    for tid in ta_dates_src:
        combined.append(("ta", tid))
    src_dates = {**{("gp", k): v for k, v in gp_dates_src.items()},
                 **{("ta", k): v for k, v in ta_dates_src.items()}}
    combined.sort(key=lambda kv: src_dates[kv], reverse=True)  # newest original first

    stamps = restamp_dates(len(combined))
    created_by_id: dict[str, datetime] = {}
    for (_, ext_id), stamp in zip(combined, stamps):
        created_by_id[ext_id] = stamp

    gp_fixture = build_gp_fixture(gp_records, created_by_id)
    ta_fixture = build_ta_fixture(ta_records, created_by_id)

    CONNECTORS_DIR.mkdir(parents=True, exist_ok=True)
    (CONNECTORS_DIR / "google_business_profile.json").write_text(
        json.dumps(gp_fixture, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (CONNECTORS_DIR / "tripadvisor.json").write_text(
        json.dumps(ta_fixture, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"Cleaned Google Places in place: {len(gp_all)} text reviews kept.")
    print(f"Wrote {CONNECTORS_DIR / 'google_business_profile.json'} "
          f"({len(gp_fixture)} records, <= {GP_FIXTURE_MAX_STARS} star only).")
    print(f"Wrote {CONNECTORS_DIR / 'tripadvisor.json'} ({len(ta_fixture)} records).")
    print(f"Re-stamped dates into {iso_z(WINDOW_START)} .. {iso_z(WINDOW_END)}.")


if __name__ == "__main__":
    main()
