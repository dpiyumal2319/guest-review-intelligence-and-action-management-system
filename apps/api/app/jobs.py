from __future__ import annotations

import argparse

from app.apify_importer import ApifyImportInput, run_apify_dataset_import
from app.connectors.registry import CONNECTORS
from app.database import SessionLocal
from app.ingestion import run_mock_connector_by_key, run_seed_ingestion
from app.reddit_import import run_reddit_social_listening_ingestion


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one ingestion source outside the web UI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("seed", help="Import the prepared demo seed dataset.")
    subparsers.add_parser("reddit", help="Import the offline Reddit social-listening fixture.")

    connector_parser = subparsers.add_parser("connector", help="Run one verified mock connector.")
    connector_parser.add_argument("connector_key", choices=sorted(CONNECTORS))

    apify_parser = subparsers.add_parser("apify", help="Import an offline Apify JSON or CSV export.")
    apify_input = apify_parser.add_mutually_exclusive_group(required=True)
    apify_input.add_argument("--file-path")
    apify_input.add_argument("--content")
    apify_parser.add_argument("--file-name")
    apify_parser.add_argument("--actor-name")
    apify_parser.add_argument("--export-date")
    apify_parser.add_argument("--platform")
    apify_parser.add_argument("--source-url")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    with SessionLocal() as session:
        if args.command == "seed":
            run = run_seed_ingestion(session)
        elif args.command == "reddit":
            run = run_reddit_social_listening_ingestion(session)
        elif args.command == "connector":
            run = run_mock_connector_by_key(session, args.connector_key)
        elif args.command == "apify":
            run = run_apify_dataset_import(
                session,
                ApifyImportInput(
                    file_path=args.file_path,
                    content=args.content,
                    file_name=args.file_name,
                    actor_name=args.actor_name,
                    export_date=args.export_date,
                    platform=args.platform,
                    source_url=args.source_url,
                ),
            )
        else:
            raise SystemExit(f"Unknown command {args.command!r}")

    print(
        f"{run.connector_key} {run.status}: "
        f"{run.records_created} created, {run.records_updated} updated, "
        f"{run.records_skipped} skipped, {run.error_count} errors"
    )


if __name__ == "__main__":
    main()
