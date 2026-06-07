#!/usr/bin/env sh
# Import all three connectors from a fixture directory.
# Usage: import_fixture_set.sh <fixture-dir>
set -eu

cd "$(dirname "$0")/.."
FIXTURE_DIR="$1"

for platform in google_business_profile booking_com tripadvisor; do
  .venv/bin/python -m app.jobs connector "$platform" --fixture-path "$FIXTURE_DIR/${platform}.json"
done
