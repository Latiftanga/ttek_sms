#!/usr/bin/env bash
# Fly.io Start Script
# Runs migrations and starts the appropriate process

set -o errexit

echo "=== Running migrations for shared schema ==="
python manage.py migrate_schemas --shared

echo "=== Running migrations for tenant schemas ==="
python manage.py migrate_schemas --tenant

echo "=== Setting up public tenant ==="
python manage.py setup_public_tenant

# Create superuser if environment variables are set
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "=== Creating superuser ==="
    python manage.py createsuperuser --noinput || echo "Superuser already exists or creation failed"
fi

echo "=== Starting Gunicorn ==="
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --threads 2 \
    --worker-class gthread \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile -
