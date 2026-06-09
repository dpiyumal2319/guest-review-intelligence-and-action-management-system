#!/usr/bin/env sh
# Dump the demo Postgres database to a versioned, gzipped SQL snapshot in the repo.
# Teammates restore this (restore_db.sh) instead of re-ingesting + re-running Gemini detection.
set -eu

cd "$(dirname "$0")/../../.."  # repo root (docker compose lives here)

SNAP_DIR="apps/api/data/db-snapshots"
mkdir -p "$SNAP_DIR"
OUT="$SNAP_DIR/guest_reviews_$(date +%Y%m%d).sql.gz"

docker compose exec -T postgres pg_dump -U guest_reviews --clean --if-exists guest_reviews \
  | gzip > "$OUT"

echo "Wrote $OUT ($(du -h "$OUT" | cut -f1))."
