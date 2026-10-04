#!/bin/sh
set -eu
if [ "$#" -ne 2 ] || [ "$1" != "--replace-database" ]; then
    printf '%s\n' 'Usage: sh deploy/restore.sh --replace-database /absolute/path/to/backup.dump' >&2
    exit 2
fi
test -f "$2"
case "$2" in /*) RESTORE_PATH=$2 ;; *) printf '%s\n' 'Use an absolute backup path.' >&2; exit 2 ;; esac
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_ROOT"
docker compose --env-file .deploy.env -f docker-compose.yml stop web api
docker compose --env-file .deploy.env -f docker-compose.yml exec -T db \
    pg_restore -U promptengine -d promptengine --clean --if-exists --no-owner --exit-on-error < "$RESTORE_PATH"
printf '%s\n' 'Database restored. Services remain stopped; verify the release/schema before restarting.'
