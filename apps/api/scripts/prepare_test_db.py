from __future__ import annotations

import argparse
import os
import sys

from psycopg import connect
from sqlalchemy.engine import make_url


DEFAULT_DATABASE_URL = "postgresql+psycopg://guest_reviews:guest_reviews@localhost:5432/guest_reviews"


def _test_database_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit

    base_url = make_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
    database_name = base_url.database or "guest_reviews"
    if not database_name.endswith("_test"):
        database_name = f"{database_name}_test"
    return str(base_url.set(database=database_name))


def _admin_database_url(test_database_url: str) -> str:
    url = make_url(test_database_url)
    admin_database = os.getenv("TEST_DATABASE_ADMIN_DB", "postgres")
    return url.set(
        drivername="postgresql",
        database=admin_database,
    ).render_as_string(hide_password=False)


def _ensure_database_exists(test_database_url: str) -> None:
    test_url = make_url(test_database_url)
    admin_url = _admin_database_url(test_database_url)

    with connect(admin_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (test_url.database,),
            )
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute(f'CREATE DATABASE "{test_url.database}"')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-url", action="store_true")
    parser.add_argument("--ensure", action="store_true")
    args = parser.parse_args(argv)

    test_database_url = _test_database_url()

    if args.print_url:
        print(test_database_url)
        return 0

    if args.ensure or not args.print_url:
        _ensure_database_exists(test_database_url)
        print(test_database_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
