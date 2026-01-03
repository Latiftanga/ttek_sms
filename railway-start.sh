#!/usr/bin/env bash
# Railway Web Service Start Script
set -o errexit

echo "=== Running database migrations ==="
python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant

echo "=== Setting up public tenant ==="
python manage.py setup_public_tenant || echo "Public tenant already exists"

echo "=== Starting Gunicorn ==="
exec gunicorn config.wsgi:application \
    --bind "[::]:${PORT:-8000}" \
    --workers 2 \
    --threads 2 \
    --worker-class gthread \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile -
