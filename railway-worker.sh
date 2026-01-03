#!/usr/bin/env bash
# Railway Worker Start Script
set -o errexit

echo "=== Starting Celery Worker ==="
exec celery -A config worker --loglevel=info --concurrency=2
