#!/usr/bin/env bash
# Daily licensed-transfer load + retraining attempt. Idempotent; safe to re-run.
#
# Scheduled by the systemd user timer gfs-daily-transfers.timer (Persistent=true,
# so a run missed while the machine was off is caught up at the next login).
# The machine is not guaranteed to have working DNS the moment the timer fires
# (boot / resume / VPN), so the API step waits for the provider host to resolve
# and retries before giving up.
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=logs/daily_transfers.log
API_HOST=v3.football.api-sports.io
DNS_TRIES=20          # x DNS_SLEEP = 5 minutes of waiting for the network
DNS_SLEEP=15
LOAD_TRIES=3
mkdir -p logs

wait_for_dns() {
  for _ in $(seq 1 "$DNS_TRIES"); do
    getent hosts "$API_HOST" >/dev/null 2>&1 && return 0
    sleep "$DNS_SLEEP"
  done
  return 1
}

load_teams() {
  for attempt in $(seq 1 "$LOAD_TRIES"); do
    .venv/bin/python scripts/gfs.py api-football load-teams --budget 95 && return 0
    echo "load-teams attempt $attempt/$LOAD_TRIES failed"
    sleep 30
  done
  return 1
}

{
  echo "=== $(date -Is) start"
  docker compose up -d db redis >/dev/null 2>&1 || true
  for i in $(seq 1 12); do docker compose ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep -q 'gfs-db healthy' && break; sleep 5; done

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

  .venv/bin/python scripts/gfs.py value-model train --val-from 2017-01-01 --test-from 2021-01-01 || echo "training skipped: $?"
  .venv/bin/python scripts/gfs.py quality-scan
  echo "=== $(date -Is) end"
} >> "$LOG" 2>&1
