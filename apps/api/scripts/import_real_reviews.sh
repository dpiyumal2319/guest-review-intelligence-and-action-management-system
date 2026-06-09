#!/usr/bin/env sh
# Import the real (crawled) Google Places + TripAdvisor reviews through the existing connectors.
# Run scripts/transform_real_reviews.py first to produce the connector fixtures.
set -eu

cd "$(dirname "$0")/.."

for platform in google_business_profile tripadvisor; do
  .venv/bin/python -m app.jobs connector "$platform" \
    --fixture-path "data/real-reviews/connectors/${platform}.json"
done
