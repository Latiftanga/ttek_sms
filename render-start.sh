#!/usr/bin/env bash
# Render Start Script
# This script runs when starting the web service on Render

set -o errexit  # Exit on error

echo "=== Running migrations for shared schema ==="
python manage.py migrate_schemas --shared

echo "=== Running migrations for tenant schemas ==="
python manage.py migrate_schemas --tenant

echo "=== Setting up public tenant ==="
python manage.py setup_public_tenant || echo "Public tenant already exists"

echo "=== Creating superuser if not exists ==="
python manage.py create_superuser_from_env || echo "Superuser creation skipped"

echo "=== Starting Gunicorn ==="
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --threads 2 \
    --worker-class gthread \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile -
