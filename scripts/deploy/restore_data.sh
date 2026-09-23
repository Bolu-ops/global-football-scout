#!/usr/bin/env bash
# Load a bundle from export_data.sh into the production stack (docker-compose.prod.yml).
# Replaces the production database contents; run it on the server in the repository clone.
#
#   scripts/deploy/restore_data.sh gfs-bundle-YYYYMMDD.tar
set -euo pipefail
cd "$(dirname "$0")/../.."
BUNDLE=${1:?usage: $0 <bundle.tar>}
[ -f .env ] || { echo ".env missing: copy .env.example and fill it in first" >&2; exit 1; }
set -a && . ./.env && set +a
USER_=${POSTGRES_USER:-gfs}
DB=${POSTGRES_DB:-gfs}
DC="docker compose -f docker-compose.prod.yml"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

tar -xf "$BUNDLE" -C "$WORK"
echo "unpacking data/ and ml/artifacts ..."
tar -xzf "$WORK/files.tar.gz"

# Nothing may hold the database open while it is replaced.
$DC stop api >/dev/null 2>&1 || true
$DC up -d --wait db
echo "restoring database $DB ..."
$DC exec -T db psql -U "$USER_" -d postgres -v ON_ERROR_STOP=1 -q \
  -c "DROP DATABASE IF EXISTS \"$DB\" WITH (FORCE)" -c "CREATE DATABASE \"$DB\""
$DC exec -T db pg_restore -U "$USER_" -d "$DB" --no-owner --exit-on-error < "$WORK/gfs.dump"

$DC up -d --build
echo "restored; the site starts at https://$DOMAIN once Caddy has its certificate"
