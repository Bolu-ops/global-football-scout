#!/usr/bin/env bash
# Run on a machine you own (e.g. your laptop) to keep off-server copies of the nightly
# backups for free: copies new bundles from the server's backups/ into BACKUP_PULL_DIR and
# keeps the newest BACKUP_PULL_KEEP there. Scheduled by the systemd user timer in
# scripts/deploy/systemd/, which catches up a run missed while the machine was off.
#
# In this repository's .env:  BACKUP_SOURCE=ubuntu@<server>:gfs/backups
set -uo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] && set -a && . ./.env && set +a
SRC=${BACKUP_SOURCE:?set BACKUP_SOURCE in .env, e.g. ubuntu@<server>:gfs/backups}
DEST=${BACKUP_PULL_DIR:-$HOME/gfs-backups}
KEEP=${BACKUP_PULL_KEEP:-30}
LOG=logs/pull_backups.log
mkdir -p "$DEST" logs

{
  echo "=== $(date -Is) start"
  ok=
  # The network may not be up yet right after boot or resume.
  for attempt in 1 2 3 4 5; do
    rsync -a --include='gfs-bundle-*.tar' --exclude='*' -e 'ssh -o BatchMode=yes -o ConnectTimeout=20' \
      "$SRC/" "$DEST/" && { ok=1; break; }
    echo "pull attempt $attempt/5 failed"
    sleep 60
  done
  if [ -z "$ok" ]; then
    echo "=== $(date -Is) end (FAILED: could not reach $SRC)"
    exit 1
  fi
  ls -1t "$DEST"/gfs-bundle-*.tar 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
  echo "have $(ls -1 "$DEST"/gfs-bundle-*.tar 2>/dev/null | wc -l) bundles in $DEST; newest $(ls -1t "$DEST"/gfs-bundle-*.tar 2>/dev/null | head -1)"
  echo "=== $(date -Is) end"
} >> "$LOG" 2>&1
