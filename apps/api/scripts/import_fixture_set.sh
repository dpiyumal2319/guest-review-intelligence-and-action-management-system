#!/usr/bin/env sh
# Import all three connectors from a fixture directory.
# Usage: import_fixture_set.sh <fixture-dir>
set -eu

FIXTURE_DIR="$1"
# Convert to absolute path before cd if relative
case "$FIXTURE_DIR" in
  /*) ;;
  *) FIXTURE_DIR="$(pwd)/$FIXTURE_DIR" ;;
esac
cd "$(dirname "$0")/.."

for platform in google_business_profile booking_com tripadvisor; do
  .venv/bin/python -m app.jobs connector "$platform" --fixture-path "$FIXTURE_DIR/${platform}.json"
done
