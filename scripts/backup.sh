#!/bin/bash
# TTEK SMS Database Backup Script
# Usage: ./scripts/backup.sh

set -e

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/ttek_sms_$DATE.sql"

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

echo "Creating database backup..."

# Create backup
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U ${POSTGRES_USER:-ttek_user} ${POSTGRES_DB:-ttek_sms_db} > $BACKUP_FILE

# Compress backup
gzip $BACKUP_FILE

echo "Backup created: ${BACKUP_FILE}.gz"

# Keep only last 7 backups
echo "Cleaning old backups (keeping last 7)..."
ls -t $BACKUP_DIR/*.gz 2>/dev/null | tail -n +8 | xargs -r rm

echo "Backup complete!"
ls -lh $BACKUP_DIR/
