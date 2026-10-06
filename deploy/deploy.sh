#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/promptengine"
LOG_DIR="${APP_DIR}/logs"
BACKUP_DIR="${APP_DIR}/backups"
LOG_FILE="${LOG_DIR}/deploy_history.log"

TARGET_SHA="${1:-$(git rev-parse HEAD)}"
TRIGGER_ACTOR="${2:-manual}"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

mkdir -p "${LOG_DIR}" "${BACKUP_DIR}"

log() {
  local level="$1"
  local message="$2"
  local entry="[${TIMESTAMP}] [${level}] [commit:${TARGET_SHA}] [by:${TRIGGER_ACTOR}] ${message}"
  echo "${entry}"
  echo "${entry}" >> "${LOG_FILE}"
}

# Capture previous release tag for rollback
PREVIOUS_SHA="$(grep -E '^RELEASE_TAG=' "${APP_DIR}/.deploy.env" 2>/dev/null | cut -d '=' -f2 || git rev-parse HEAD)"
PRE_DEPLOY_BACKUP="${BACKUP_DIR}/pre_deploy_${TIMESTAMP}_${TARGET_SHA:0:7}.dump"

rollback() {
  local exit_code=$?
  log "ERROR" "Deployment failed at step with exit code ${exit_code}. Initiating rollback..."
  
  if [ -n "${PREVIOUS_SHA}" ]; then
    log "INFO" "Rolling back .deploy.env RELEASE_TAG to ${PREVIOUS_SHA}"
    sed -i "s/^RELEASE_TAG=.*/RELEASE_TAG=${PREVIOUS_SHA}/" "${APP_DIR}/.deploy.env"
    docker compose --env-file .deploy.env up -d --no-deps --force-recreate --wait api web || true
  fi
  
  log "FAILED" "Deployment aborted. Rollback applied. Database backup kept at: ${PRE_DEPLOY_BACKUP}"
  exit "${exit_code}"
}

trap rollback ERR

cd "${APP_DIR}"
log "START" "Starting production deployment process"

# Step 1: Pre-flight Database Backup and Integrity Verification
log "STEP" "Creating pre-deployment verified database backup"
docker compose --env-file .deploy.env exec -T db pg_dump \
  -U promptengine -Fc promptengine > "${PRE_DEPLOY_BACKUP}"

chmod 600 "${PRE_DEPLOY_BACKUP}"

# Verify archive integrity (pg_restore --list reads header/catalog without restoring)
docker compose --env-file .deploy.env exec -T db pg_restore \
  --list < "${PRE_DEPLOY_BACKUP}" > /dev/null

log "STEP" "Database backup verified successfully (${PRE_DEPLOY_BACKUP})"

# Step 2: Fetch and align repository to Target SHA
log "STEP" "Syncing codebase to commit ${TARGET_SHA}"
git fetch origin main
git reset --hard "${TARGET_SHA}"

# Step 3: Update immutable release tag in environment
log "STEP" "Setting RELEASE_TAG to ${TARGET_SHA}"
if grep -q "^RELEASE_TAG=" .deploy.env; then
  sed -i "s/^RELEASE_TAG=.*/RELEASE_TAG=${TARGET_SHA}/" .deploy.env
else
  echo "RELEASE_TAG=${TARGET_SHA}" >> .deploy.env
fi

# Step 4: Build immutable container images
log "STEP" "Building Docker images"
docker compose --env-file .deploy.env build

# Step 5: Execute database migrations
log "STEP" "Applying Alembic schema migrations"
docker compose --env-file .deploy.env run --rm --no-deps migrate

# Step 6: Dynamic rolling update
log "STEP" "Recreating API and Web services with zero downtime"
docker compose --env-file .deploy.env up -d --no-deps --force-recreate --wait --wait-timeout 120 api web

# Step 7: Post-deployment ingress & health checks
log "STEP" "Validating Nginx routing and API readiness"
docker compose --env-file .deploy.env exec -T web nginx -t
docker compose --env-file .deploy.env exec -T api flask --app wsgi db current

log "SUCCESS" "Deployment completed successfully. Services healthy."
