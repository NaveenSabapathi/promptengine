#!/bin/sh
# Operator release entry point, invoked by protected GitHub Actions over SSH.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
case "${1:-}" in *[!a-f0-9]*|'') echo 'Pass a full commit SHA' >&2; exit 2 ;; esac
test ${#1} -eq 40
SHA=$1
mkdir -p deploy/state
exec 9>deploy/state/release.lock
flock -n 9 || { echo 'Another release is running' >&2; exit 1; }
test -z "$(git status --porcelain --untracked-files=no)" || { echo 'Tracked host files have changes' >&2; exit 1; }
OLD_SHA=$(git rev-parse HEAD)
OLD_TAG=$(sed -n 's/^RELEASE_TAG=//p' .deploy.env)
test -n "$OLD_TAG"
git fetch origin main
git merge-base --is-ancestor "$SHA" origin/main
BACKUP_REQUIRE_WAIT=true sh deploy/backup-cron.sh
ARCHIVE=$(find backups -name 'promptengine-*.dump' -type f | sort | tail -n 1)
printf '%s\n' "previous_sha=$OLD_SHA" "previous_tag=$OLD_TAG" "target_sha=$SHA" "rescue_backup=$ARCHIVE" > deploy/state/pending
# The new images must have passed the application and deployment workflows.
git checkout --detach "$SHA"
python3 deploy/enterprise-init.py
sed -i "s/^RELEASE_TAG=.*/RELEASE_TAG=$SHA/" .deploy.env
compose() {
    if grep -qx 'SECONDARY_ENABLED=true' .deploy.env; then
        docker compose --env-file .deploy.env -f docker-compose.yml -f docker-compose.replica.yml "$@"
    else
        docker compose --env-file .deploy.env -f docker-compose.yml "$@"
    fi
}
compose config --quiet
compose pull api web migrate
compose stop web api
# Migrations are forward-only. On failure preserve the rescue backup and stop;
# never attempt a destructive schema downgrade or silently restore old user data.
if ! compose run --rm --no-deps migrate; then
    echo 'Migration failed; services stopped. Review deploy/state/pending and restore runbook.' >&2
    exit 1
fi
if ! compose up -d --wait --wait-timeout 180 api web; then
    echo 'Release health failed; services stopped for operator recovery. Database is retained.' >&2
    compose stop web api
    exit 1
fi
printf '%s\n' "$SHA" > deploy/state/current.tmp
mv deploy/state/current.tmp deploy/state/current
mv deploy/state/pending deploy/state/previous
printf '%s\n' 'Release healthy; recovery state retained.'
