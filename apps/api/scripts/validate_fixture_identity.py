from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps/api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.connectors.registry import get_connector  # noqa: E402


PLATFORMS = ("google_business_profile", "booking_com", "tripadvisor")


def fixture_identity(directory: Path) -> dict[tuple[str, str], str]:
    identities: dict[tuple[str, str], str] = {}
    for platform in PLATFORMS:
        connector = get_connector(platform)
        path = directory / f"{platform}.json"
        payloads = json.loads(path.read_text(encoding="utf-8"))
        for index, payload in enumerate(payloads, start=1):
            normalized = connector.normalize(payload)
            key = (normalized["source_code"], normalized["external_review_id"])
            origin = f"{path}:{index}"
            if key in identities:
                raise ValueError(f"Duplicate identity inside fixture set: {key} at {identities[key]} and {origin}")
            identities[key] = origin
    return identities


def validate(directories: list[Path]) -> None:
    seen: dict[tuple[str, str], str] = {}
    for directory in directories:
        for key, origin in fixture_identity(directory).items():
            if key in seen:
                raise ValueError(f"Fixture identity collision for {key}: {seen[key]} and {origin}")
            seen[key] = origin


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail if connector fixture directories share source/external-review IDs.")
    parser.add_argument("directories", nargs="+", type=Path)
    args = parser.parse_args()
    validate([directory.resolve() for directory in args.directories])
    print(f"validated {len(args.directories)} fixture directories without identity collisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
