#!/usr/bin/env bash
# Railway Beat Start Script
set -o errexit

echo "=== Starting Celery Beat ==="
exec celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
