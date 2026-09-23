#!/usr/bin/env bash
# Bundle this machine's data for the production server: a dump of the development
# database, data/ without the StatsBomb raw files (12 GB, only needed to re-ingest; the
# derived rows are in the dump) and ml/artifacts.
#
#   scripts/deploy/export_data.sh                 # writes gfs-bundle-YYYYMMDD.tar
#   scp gfs-bundle-*.tar user@server:gfs/          # then restore_data.sh on the server
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] && set -a && . ./.env && set +a
USER_=${POSTGRES_USER:-gfs}
DB=${POSTGRES_DB:-gfs}
OUT=${1:-gfs-bundle-$(date +%Y%m%d).tar}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

docker compose up -d --wait db >/dev/null
echo "dumping database $DB ..."
docker compose exec -T db pg_dump -U "$USER_" -d "$DB" -Fc -Z 6 > "$WORK/gfs.dump"

echo "packing data/ (without data/raw/statsbomb) and ml/artifacts ..."
tar -czf "$WORK/files.tar.gz" --exclude=data/raw/statsbomb data ml/artifacts

tar -cf "$OUT" -C "$WORK" gfs.dump files.tar.gz
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
