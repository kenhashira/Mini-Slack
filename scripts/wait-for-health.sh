#!/usr/bin/env bash
# Poll GET /health until it returns 200, or fail after N seconds.
# Usage: scripts/wait-for-health.sh [url] [seconds]
set -u
url="${1:-http://localhost:8000/health}"
tries="${2:-30}"

for i in $(seq 1 "$tries"); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)"
  if [ "$code" = "200" ]; then
    echo "GET $url -> 200 (attempt $i)"
    exit 0
  fi
  echo "attempt $i/$tries: GET $url -> $code"
  sleep 1
done

echo "GET $url never returned 200 within ${tries}s" >&2
exit 1
