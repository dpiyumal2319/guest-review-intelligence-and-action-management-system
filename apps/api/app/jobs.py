from __future__ import annotations

import argparse

from app.connectors.registry import CONNECTORS
from app.database import SessionLocal
from app.ingestion import run_mock_connector_by_key


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one ingestion source outside the web UI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    connector_parser = subparsers.add_parser("connector", help="Run one review-platform connector.")
    connector_parser.add_argument("connector_key", choices=sorted(CONNECTORS))
    connector_parser.add_argument("--fixture-path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    with SessionLocal() as session:
        if args.command == "connector":
            run = run_mock_connector_by_key(session, args.connector_key, fixture_path=args.fixture_path)
        else:
            raise SystemExit(f"Unknown command {args.command!r}")

    print(
        f"{run.connector_key} {run.status}: "
        f"{run.records_created} created, {run.records_updated} updated, "
        f"{run.records_skipped} skipped, {run.error_count} errors"
    )


if __name__ == "__main__":
    main()
