from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "apps/api/data/generated-fixtures/connectors-llama"


def prefixed(value: str, prefix: str = "llama-") -> str:
    return value if value.startswith(prefix) else f"{prefix}{value}"


def namespace_google(payload: dict[str, Any]) -> None:
    old_id = payload["reviewId"]
    new_id = prefixed(old_id)
    payload["reviewId"] = new_id
    if isinstance(payload.get("name"), str):
        payload["name"] = payload["name"].removesuffix(old_id) + new_id


def namespace_booking(payload: dict[str, Any]) -> None:
    payload["guest_review_id"] = prefixed(payload["guest_review_id"])
    if isinstance(payload.get("reservation_id"), str):
        payload["reservation_id"] = prefixed(payload["reservation_id"], "llama-")


def namespace_tripadvisor(payload: dict[str, Any]) -> None:
    old_id = payload["id"]
    new_id = prefixed(old_id)
    payload["id"] = new_id
    match = re.search(r"tripadvisor-review-(\d+)$", old_id)
    if match and isinstance(payload.get("url"), str):
        payload["url"] = payload["url"].replace(f"-r{match.group(1)}-", f"-rllama-{match.group(1)}-")


def namespace_file(path: Path, platform: str) -> None:
    payloads = json.loads(path.read_text(encoding="utf-8"))
    for payload in payloads:
        if platform == "google_business_profile":
            namespace_google(payload)
        elif platform == "booking_com":
            namespace_booking(payload)
        elif platform == "tripadvisor":
            namespace_tripadvisor(payload)
        else:
            raise ValueError(f"Unsupported platform {platform!r}")
    path.write_text(json.dumps(payloads, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    namespace_file(FIXTURE_DIR / "google_business_profile.json", "google_business_profile")
    namespace_file(FIXTURE_DIR / "booking_com.json", "booking_com")
    namespace_file(FIXTURE_DIR / "tripadvisor.json", "tripadvisor")

    manifest_path = FIXTURE_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["id_namespace"] = "llama"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"namespaced llama fixture IDs: {FIXTURE_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
