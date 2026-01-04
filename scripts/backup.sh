#!/bin/bash
set -e

# Configuration
BACKUP_DIR="/home/deploy/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

echo "=== Starting database backup ==="

# Dump the database
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres school_db | gzip > "$BACKUP_DIR/db_backup_$DATE.sql.gz"

echo "Backup created: $BACKUP_DIR/db_backup_$DATE.sql.gz"

# Remove old backups
echo "Removing backups older than $RETENTION_DAYS days..."
find $BACKUP_DIR -name "db_backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "=== Backup complete ==="
ls -lh $BACKUP_DIR
