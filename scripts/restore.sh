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

# Check for backup file argument
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file.sql.gz>"
    echo ""
    echo "Available backups:"
    ls -lh "${BACKUP_DIR}"/ttek_sms_*.sql.gz 2>/dev/null || echo "No backups found in ${BACKUP_DIR}"
    exit 1
fi

BACKUP_FILE="$1"

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

log_info "Restoring from: ${BACKUP_FILE}"
log_info "Target database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"

# Confirm restore
read -p "This will OVERWRITE the current database. Are you sure? (yes/no): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    log_info "Restore cancelled"
    exit 0
fi

export PGPASSWORD="${POSTGRES_PASSWORD}"

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
