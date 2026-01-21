#!/bin/bash
# Database backup script for TTEK SMS
# Supports local backups and optional S3 upload

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="ttek_sms_${TIMESTAMP}.sql.gz"

# Database connection (from environment)
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-ttek_sms}"
DB_USER="${POSTGRES_USER:-postgres}"

log_info() { echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $1"; }
log_warn() { echo "[WARN] $(date '+%Y-%m-%d %H:%M:%S') - $1"; }
log_error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $1"; }

# Create backup directory
mkdir -p "${BACKUP_DIR}"

log_info "Starting database backup..."
log_info "Database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"

# Perform backup
export PGPASSWORD="${POSTGRES_PASSWORD}"

if pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" | gzip > "${BACKUP_DIR}/${BACKUP_NAME}"; then
    BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}" | cut -f1)
    log_info "Backup created: ${BACKUP_NAME} (${BACKUP_SIZE})"
else
    log_error "Backup failed!"
    exit 1
fi

# Upload to S3 if configured
if [ -n "${S3_BUCKET}" ] && command -v aws &> /dev/null; then
    log_info "Uploading to S3: s3://${S3_BUCKET}/backups/"
    if aws s3 cp "${BACKUP_DIR}/${BACKUP_NAME}" "s3://${S3_BUCKET}/backups/${BACKUP_NAME}"; then
        log_info "S3 upload successful"
    else
        log_warn "S3 upload failed"
    fi
fi

# Clean up old local backups
log_info "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "ttek_sms_*.sql.gz" -mtime +${RETENTION_DAYS} -delete

# List current backups
log_info "Current backups:"
ls -lh "${BACKUP_DIR}"/ttek_sms_*.sql.gz 2>/dev/null | tail -5 || log_warn "No backups found"

log_info "Backup complete!"
