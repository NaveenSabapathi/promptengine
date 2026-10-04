#!/bin/sh
set -eu
umask 077
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_ROOT"
mkdir -p backups
chmod 700 backups
BACKUP_PATH="backups/promptengine-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
trap 'rm -f "$BACKUP_PATH.tmp"' EXIT HUP INT TERM
docker compose --env-file .deploy.env -f docker-compose.yml exec -T db \
    pg_dump -U promptengine -d promptengine --format=custom --no-owner > "$BACKUP_PATH.tmp"
test -s "$BACKUP_PATH.tmp"
mv "$BACKUP_PATH.tmp" "$BACKUP_PATH"
printf '%s\n' "$BACKUP_PATH"
