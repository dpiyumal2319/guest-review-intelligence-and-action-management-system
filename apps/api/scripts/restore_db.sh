#!/usr/bin/env sh
# Restore the demo Postgres database from a gzipped SQL snapshot.
# Usage: restore_db.sh [snapshot.sql.gz]   (defaults to the newest snapshot in db-snapshots/)
# The dump was taken with --clean --if-exists, so this is idempotent on a non-empty DB.
set -eu

cd "$(dirname "$0")/../../.."  # repo root

SNAP_DIR="apps/api/data/db-snapshots"
SNAPSHOT="${1:-$(ls -1t "$SNAP_DIR"/*.sql.gz 2>/dev/null | head -n1)}"

if [ -z "${SNAPSHOT:-}" ] || [ ! -f "$SNAPSHOT" ]; then
  echo "No snapshot found. Pass a path or place one in $SNAP_DIR/." >&2
  exit 1
fi

echo "Restoring from $SNAPSHOT ..."
gunzip -c "$SNAPSHOT" | docker compose exec -T postgres psql -U guest_reviews -d guest_reviews
echo "Restore complete."
