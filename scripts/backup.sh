#!/bin/bash
# Database backup script for TTEK SMS
# Supports local backups and optional S3 upload

set -e

# Parse arguments
SCHEMA=""
while [ $# -gt 0 ]; do
    case "$1" in
        --schema)
            SCHEMA="$2"
            shift 2
            ;;
        *)
            echo "Usage: $0 [--schema <schema_name>]"
            exit 1
            ;;
    esac
done

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

if [ -n "${SCHEMA}" ]; then
    BACKUP_NAME="ttek_sms_${SCHEMA}_${TIMESTAMP}.dump"
else
    BACKUP_NAME="ttek_sms_${TIMESTAMP}.sql.gz"
fi

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

export PGPASSWORD="${POSTGRES_PASSWORD}"

if [ -n "${SCHEMA}" ]; then
    log_info "Starting schema backup: ${SCHEMA}"
    log_info "Database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"

    if pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -Fc --schema="${SCHEMA}" > "${BACKUP_DIR}/${BACKUP_NAME}"; then
        BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}" | cut -f1)
        log_info "Schema backup created: ${BACKUP_NAME} (${BACKUP_SIZE})"
    else
        log_error "Schema backup failed!"
        exit 1
    fi
else
    log_info "Starting full database backup..."
    log_info "Database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"

    if pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" | gzip > "${BACKUP_DIR}/${BACKUP_NAME}"; then
        BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}" | cut -f1)
        log_info "Backup created: ${BACKUP_NAME} (${BACKUP_SIZE})"
    else
        log_error "Backup failed!"
        exit 1
    fi
fi

# Upload to S3/R2 if configured
if [ -n "${S3_BUCKET}" ] && command -v aws &> /dev/null; then
    S3_ARGS=""
    if [ -n "${S3_ENDPOINT_URL}" ]; then
        S3_ARGS="--endpoint-url ${S3_ENDPOINT_URL}"
    fi

    log_info "Uploading to S3: s3://${S3_BUCKET}/backups/"
    if aws ${S3_ARGS} s3 cp "${BACKUP_DIR}/${BACKUP_NAME}" "s3://${S3_BUCKET}/backups/${BACKUP_NAME}"; then
        log_info "S3 upload successful"
    else
        log_warn "S3 upload failed"
    fi

    # Clean up remote backups older than 30 days
    REMOTE_RETENTION_DAYS="${REMOTE_RETENTION_DAYS:-30}"
    CUTOFF_DATE=$(date -d "-${REMOTE_RETENTION_DAYS} days" +%Y%m%d 2>/dev/null || date -d "@$(( $(date +%s) - REMOTE_RETENTION_DAYS * 86400 ))" +%Y%m%d)
    log_info "Cleaning up remote backups older than ${REMOTE_RETENTION_DAYS} days (before ${CUTOFF_DATE})..."
    aws ${S3_ARGS} s3 ls "s3://${S3_BUCKET}/backups/" 2>/dev/null | while read -r line; do
        FILE_NAME=$(echo "${line}" | awk '{print $4}')
        # Extract date from filename: ttek_sms_YYYYMMDD_HHMMSS.sql.gz or ttek_sms_<schema>_YYYYMMDD_HHMMSS.dump
        FILE_DATE=$(echo "${FILE_NAME}" | grep -oP '\d{8}(?=_\d{6})')
        if [ -n "${FILE_DATE}" ] && [ "${FILE_DATE}" -lt "${CUTOFF_DATE}" ]; then
            log_info "Deleting old remote backup: ${FILE_NAME}"
            aws ${S3_ARGS} s3 rm "s3://${S3_BUCKET}/backups/${FILE_NAME}"
        fi
    done
fi

# Clean up old local backups
log_info "Cleaning up backups older than ${RETENTION_DAYS} days..."
if [ -n "${SCHEMA}" ]; then
    find "${BACKUP_DIR}" -name "ttek_sms_${SCHEMA}_*.dump" -mtime +${RETENTION_DAYS} -delete
else
    find "${BACKUP_DIR}" -name "ttek_sms_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
fi

# List current backups
log_info "Current backups:"
if [ -n "${SCHEMA}" ]; then
    ls -lh "${BACKUP_DIR}"/ttek_sms_${SCHEMA}_*.dump 2>/dev/null | tail -5 || log_warn "No schema backups found"
else
    ls -lh "${BACKUP_DIR}"/ttek_sms_*.sql.gz 2>/dev/null | tail -5 || log_warn "No backups found"
fi

log_info "Backup complete!"
