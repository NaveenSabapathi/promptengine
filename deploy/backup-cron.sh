#!/bin/sh
# Host cron entry point: exclusive lock; verify a full restore before retention.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
mkdir -p backups
exec 9>backups/.cron.lock
flock -n 9 || exit 0
ARCHIVE=$(sh deploy/backup.sh)
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
sh deploy/verify-backup.sh "$(pwd)/$ARCHIVE"
# Optional restic encryption/offsite upload. Cron must provide these through a
# protected environment file; no passwords or repository credentials in git.
if [ -n "${RESTIC_REPOSITORY:-}" ]; then
    restic backup "$ARCHIVE" "$ARCHIVE.sha256" .deploy.env deploy/secrets deploy/tls deploy/state --tag promptlogic-postgres
    restic check
    restic forget --tag promptlogic-postgres --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune
fi
# Delete only completed, verified archives after successful optional remote upload.
find backups -name 'promptengine-*.dump' -mtime +30 -exec rm -- {} \;
find backups -name 'promptengine-*.dump.sha256' -mtime +30 -exec rm -- {} \;
printf '%s\n' "$(date -u +%FT%TZ) backup verified" > backups/last-success
