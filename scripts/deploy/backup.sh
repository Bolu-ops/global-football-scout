#!/usr/bin/env bash
# Nightly backup of the production stack, in the same bundle format as export_data.sh, so
# restore_data.sh restores either. Keeps the newest BACKUP_KEEP bundles in backups/ and,
# when BACKUP_REMOTE is set (an rsync target such as user@host:gfs-backups), mirrors
# backups/ there so a lost server disk does not take the backups with it.
#
#   30 3 * * * /path/to/repo/scripts/deploy/backup.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] && set -a && . ./.env && set +a
export COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.prod.yml}
KEEP=${BACKUP_KEEP:-14}
DIR=backups
LOG=logs/backup.log
mkdir -p "$DIR" logs

{
  echo "=== $(date -Is) start"
  out="$DIR/gfs-bundle-$(date +%Y%m%d-%H%M%S).tar"
  if ! scripts/deploy/export_data.sh "$out"; then
    rm -f "$out"
    echo "=== $(date -Is) end (FAILED: export)"
    exit 1
  fi
  # An unreadable dump is worse than none: it looks like a backup until the day it is needed.
  if ! tar -xOf "$out" gfs.dump | docker compose exec -T db pg_restore -f /dev/null; then
    mv "$out" "$out.corrupt"
    echo "=== $(date -Is) end (FAILED: dump does not read back)"
    exit 1
  fi
  ls -1t "$DIR"/gfs-bundle-*.tar | tail -n +$((KEEP + 1)) | xargs -r rm -f
  if [ -n "${BACKUP_REMOTE:-}" ]; then
    rsync -a --delete --include='gfs-bundle-*.tar' --exclude='*' "$DIR/" "$BACKUP_REMOTE/" \
      || { echo "=== $(date -Is) end (FAILED: copy to $BACKUP_REMOTE)"; exit 1; }
  fi
  echo "kept $(ls -1 "$DIR"/gfs-bundle-*.tar | wc -l) bundles; newest $out ($(du -h "$out" | cut -f1))"
  echo "=== $(date -Is) end"
} >> "$LOG" 2>&1
