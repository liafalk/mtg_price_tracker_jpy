#!/usr/bin/env bash
set -Eeuo pipefail

if [ "${BACKUP_CONTAINER:-0}" = "1" ]; then
  BACKUP_DIR="${BACKUP_DIR:-/backups}"
  RETENTION_DAYS="${RETENTION_DAYS:-14}"
  POSTGRES_DB="${POSTGRES_DB:-${PGDATABASE:-jpy_mtg_prices}}"
  TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
  BACKUP_FILE="${BACKUP_DIR}/${POSTGRES_DB}-${TIMESTAMP}.dump"
  TEMP_FILE="${BACKUP_FILE}.tmp"

  mkdir -p "${BACKUP_DIR}"
  trap 'rm -f "${TEMP_FILE}"' EXIT

  pg_dump --format=custom --file="${TEMP_FILE}"
  mv "${TEMP_FILE}" "${BACKUP_FILE}"
  find "${BACKUP_DIR}" -type f -name "*.dump" -mtime +"${RETENTION_DAYS}" -delete

  trap - EXIT
  echo "Backup created: ${BACKUP_FILE}"
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if [ -f ".env" ]; then
  set -a
  . ./.env
  set +a
fi

export BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"

docker compose --profile backup run --rm \
  -e BACKUP_CONTAINER=1 backup /usr/local/bin/backup_db.sh
