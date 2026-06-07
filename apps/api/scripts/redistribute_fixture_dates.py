from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DIRS = (
    ROOT / "apps/api/data/generated-fixtures/connectors-dolphin",
    ROOT / "apps/api/data/generated-fixtures/connectors-llama",
)
PLATFORMS = ("google_business_profile", "booking_com", "tripadvisor")
WINDOW_START = datetime(2025, 6, 5, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 6, 5, 23, 59, 59, tzinfo=UTC)


def distributed_datetime(index: int, total: int) -> datetime:
    if total <= 1:
        return WINDOW_START
    return WINDOW_START + (WINDOW_END - WINDOW_START) * ((index - 1) / (total - 1))


def iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def clamp(value: datetime) -> datetime:
    return min(value, WINDOW_END)


def update_payload_dates(platform: str, payload: dict[str, Any], created: datetime) -> None:
    if platform == "google_business_profile":
        payload["createTime"] = iso_z(created)
        payload["updateTime"] = iso_z(clamp(created + timedelta(hours=12)))
        if isinstance(payload.get("reviewReply"), dict):
            payload["reviewReply"]["updateTime"] = iso_z(clamp(created + timedelta(days=1)))
        return

    if platform == "booking_com":
        payload["created_at"] = created.isoformat()
        payload["updated_at"] = clamp(created + timedelta(hours=12)).isoformat()
        return

    if platform == "tripadvisor":
        payload["published_date"] = created.isoformat()
        payload["travel_date"] = created.strftime("%Y-%m")
        if isinstance(payload.get("management_response"), dict):
            payload["management_response"]["published_date"] = clamp(created + timedelta(days=1)).isoformat()
        return

    raise ValueError(f"Unsupported platform {platform!r}")


def redistribute_directory(directory: Path) -> None:
    payloads_by_platform: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for platform in PLATFORMS:
        path = directory / f"{platform}.json"
        payloads = json.loads(path.read_text(encoding="utf-8"))
        payloads_by_platform[platform] = payloads
        total += len(payloads)

    global_index = 1
    counts: dict[str, int] = {}
    for platform in PLATFORMS:
        payloads = payloads_by_platform[platform]
        counts[platform] = len(payloads)
        for payload in payloads:
            update_payload_dates(platform, payload, distributed_datetime(global_index, total))
            global_index += 1
        (directory / f"{platform}.json").write_text(
            json.dumps(payloads, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "counts": counts,
            "total_reviews": total,
            "date_window_start": WINDOW_START.isoformat(),
            "date_window_end": WINDOW_END.isoformat(),
            "dates_redistributed_at": datetime.now(UTC).isoformat(),
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    for directory in DEFAULT_DIRS:
        redistribute_directory(directory)
        print(f"redistributed fixture dates: {directory.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
