#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if [ -f ".env" ]; then
  set -a
  . ./.env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-jpy_mtg}"
POSTGRES_DB="${POSTGRES_DB:-jpy_mtg_prices}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/jpy-mtg}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"

mkdir -p "${BACKUP_DIR}"

# Make sure the DB container is running before we dump.
docker compose exec -T db pg_dump \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --clean \
  --if-exists \
  | gzip > "${BACKUP_DIR}/${POSTGRES_DB}-${TIMESTAMP}.sql.gz"

find "${BACKUP_DIR}" -type f -name "*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete

echo "Backup created: ${BACKUP_DIR}/${POSTGRES_DB}-${TIMESTAMP}.sql.gz"
