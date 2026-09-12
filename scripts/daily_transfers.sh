#!/usr/bin/env bash
# Daily licensed-transfer load + retraining attempt. Idempotent; safe to re-run.
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=logs/daily_transfers.log
mkdir -p logs
{
  echo "=== $(date -Is) start"
  docker compose up -d db redis >/dev/null 2>&1 || true
  for i in $(seq 1 12); do docker compose ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep -q 'gfs-db healthy' && break; sleep 5; done
  .venv/bin/python scripts/gfs.py api-football load-teams --budget 95
  .venv/bin/python scripts/gfs.py value-model train --val-from 2017-01-01 --test-from 2021-01-01 || echo "training skipped: $?"
  .venv/bin/python scripts/gfs.py quality-scan
  echo "=== $(date -Is) end"
} >> "$LOG" 2>&1
