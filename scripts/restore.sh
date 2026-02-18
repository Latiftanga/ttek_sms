#!/bin/bash
# Database restore script for TTEK SMS

set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-ttek_sms}"
DB_USER="${POSTGRES_USER:-postgres}"

log_info() { echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $1"; }
log_error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $1"; }

# Parse arguments
SCHEMA=""
BACKUP_FILE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --schema)
            SCHEMA="$2"
            shift 2
            ;;
        *)
            BACKUP_FILE="$1"
            shift
            ;;
    esac
done

# Check for backup file argument
if [ -z "${BACKUP_FILE}" ]; then
    if [ -n "${SCHEMA}" ]; then
        echo "Usage: $0 --schema <schema_name> <backup_file.dump>"
        echo ""
        echo "Available schema backups:"
        ls -lh "${BACKUP_DIR}"/ttek_sms_*_*.dump 2>/dev/null || echo "No schema backups found in ${BACKUP_DIR}"
    else
        echo "Usage: $0 [--schema <schema_name>] <backup_file>"
        echo ""
        echo "Available backups:"
        ls -lh "${BACKUP_DIR}"/ttek_sms_*.sql.gz 2>/dev/null || echo "No backups found in ${BACKUP_DIR}"
    fi
    exit 1
fi

# Check if file exists
if [ ! -f "${BACKUP_FILE}" ]; then
    # Try with backup dir prefix
    if [ -f "${BACKUP_DIR}/${BACKUP_FILE}" ]; then
        BACKUP_FILE="${BACKUP_DIR}/${BACKUP_FILE}"
    else
        log_error "Backup file not found: ${BACKUP_FILE}"
        exit 1
    fi
fi

# Validate file format matches restore mode
if [ -n "${SCHEMA}" ]; then
    case "${BACKUP_FILE}" in
        *.dump) ;;
        *)
            log_error "Schema restore requires a .dump file (custom format). Got: ${BACKUP_FILE}"
            exit 1
            ;;
    esac
fi

export PGPASSWORD="${POSTGRES_PASSWORD}"

if [ -n "${SCHEMA}" ]; then
    log_info "Restoring schema '${SCHEMA}' from: ${BACKUP_FILE}"
    log_info "Target database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"

    read -p "This will OVERWRITE schema '${SCHEMA}' in the database. Other schemas are NOT affected. Are you sure? (yes/no): " CONFIRM
    if [ "${CONFIRM}" != "yes" ]; then
        log_info "Restore cancelled"
        exit 0
    fi

    log_info "Dropping schema '${SCHEMA}'..."
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -c "DROP SCHEMA IF EXISTS \"${SCHEMA}\" CASCADE;"

    log_info "Restoring schema '${SCHEMA}'..."
    if pg_restore -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" --schema="${SCHEMA}" "${BACKUP_FILE}"; then
        log_info "Schema '${SCHEMA}' restored successfully!"
    else
        log_error "Schema restore failed!"
        exit 1
    fi
else
    log_info "Restoring from: ${BACKUP_FILE}"
    log_info "Target database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"

    read -p "This will OVERWRITE the entire database. Are you sure? (yes/no): " CONFIRM
    if [ "${CONFIRM}" != "yes" ]; then
        log_info "Restore cancelled"
        exit 0
    fi

    # Drop and recreate database
    log_info "Dropping existing database..."
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};"
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -c "CREATE DATABASE ${DB_NAME};"

    # Restore
    log_info "Restoring database..."
    if gunzip -c "${BACKUP_FILE}" | psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}"; then
        log_info "Restore complete!"
    else
        log_error "Restore failed!"
        exit 1
    fi
fi
