#!/usr/bin/env bash
# Server version of scripts/daily_transfers.sh: the same load + retrain, run inside the
# production API image against the production database. Scheduled from the host crontab:
#
#   5 1 * * * /path/to/repo/scripts/deploy/daily_transfers_prod.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
LOG=logs/daily_transfers.log
API_HOST=v3.football.api-sports.io
DNS_TRIES=20          # x DNS_SLEEP = 5 minutes of waiting for the network
DNS_SLEEP=15
LOAD_TRIES=3
mkdir -p logs

gfs() { docker compose -f docker-compose.prod.yml run --rm -T api python scripts/gfs.py "$@"; }

wait_for_dns() {
  for _ in $(seq 1 "$DNS_TRIES"); do
    getent hosts "$API_HOST" >/dev/null 2>&1 && return 0
    sleep "$DNS_SLEEP"
  done
  return 1
}

load_teams() {
  for attempt in $(seq 1 "$LOAD_TRIES"); do
    gfs api-football load-teams --budget 95 && return 0
    echo "load-teams attempt $attempt/$LOAD_TRIES failed"
    sleep 30
  done
  return 1
}

{
  echo "=== $(date -Is) start"
  if ! wait_for_dns; then
    echo "network unavailable: $API_HOST did not resolve after $((DNS_TRIES * DNS_SLEEP))s; skipping run"
    echo "=== $(date -Is) end (skipped)"
    exit 0
  fi

  if ! load_teams; then
    echo "load-teams failed after $LOAD_TRIES attempts; skipping retrain (no new data)"
    echo "=== $(date -Is) end (load failed)"
    exit 0
  fi

  gfs value-model train --val-from 2017-01-01 --test-from 2021-01-01 || echo "training skipped: $?"
  gfs quality-scan
  echo "=== $(date -Is) end"
} >> "$LOG" 2>&1
