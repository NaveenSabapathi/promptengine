#!/bin/sh
# Restore into a disposable database, never the production database.
set -eu
test "$#" -eq 1 && test -s "$1"
ARCHIVE=$1
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
TEST_DB="restore_verify_$(date +%s)_$$"
compose() { docker compose --env-file .deploy.env -f docker-compose.yml "$@"; }
cleanup() { compose exec -T db dropdb -U postgres --if-exists "$TEST_DB" >/dev/null; }
trap cleanup EXIT HUP INT TERM
compose exec -T db createdb -U postgres -O promptengine "$TEST_DB"
compose exec -T db pg_restore -U postgres -d "$TEST_DB" --no-owner --exit-on-error --single-transaction < "$ARCHIVE"
compose exec -T db psql -U postgres -d "$TEST_DB" -v ON_ERROR_STOP=1 -c 'SELECT version_num FROM alembic_version; SELECT count(*) FROM users; SELECT count(*) FROM entitlements;'
