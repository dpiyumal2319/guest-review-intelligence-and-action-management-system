#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../../.."

docker compose up -d postgres_test >/dev/null

container_id="$(docker compose ps -q postgres_test)"
if [ -z "$container_id" ]; then
  echo "failed to resolve postgres_test container id" >&2
  exit 1
fi

attempts=0
while [ "$attempts" -lt 60 ]; do
  status="$(docker inspect -f '{{.State.Health.Status}}' "$container_id" 2>/dev/null || true)"
  if [ "$status" = "healthy" ]; then
    exit 0
  fi
  attempts=$((attempts + 1))
  sleep 1
done

echo "postgres_test did not become healthy within 60 seconds" >&2
exit 1
