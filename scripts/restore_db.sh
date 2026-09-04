#!/usr/bin/env bash
set -Eeuo pipefail

if [ "${BACKUP_CONTAINER:-0}" = "1" ]; then
  if [ "$#" -ne 1 ]; then
    echo "Usage: restore_db.sh /backups/database-TIMESTAMP.dump" >&2
    exit 1
  fi
  pg_restore --clean --if-exists --no-owner --exit-on-error --jobs="${RESTORE_JOBS:-4}" "$1"
  echo "Restore completed from $1"
  exit 0
fi

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/backup.dump" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
if [ -f "${PROJECT_ROOT}/.env" ]; then
  set -a
  . "${PROJECT_ROOT}/.env"
  set +a
fi

BACKUP_FILE="$(realpath "$1")"
BACKUP_DIR="$(dirname "${BACKUP_FILE}")"
BACKUP_NAME="$(basename "${BACKUP_FILE}")"

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "Backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi

cd "${PROJECT_ROOT}"
export BACKUP_DIR
docker compose --profile backup run --rm \
  -e BACKUP_CONTAINER=1 backup /usr/local/bin/restore_db.sh "/backups/${BACKUP_NAME}"
