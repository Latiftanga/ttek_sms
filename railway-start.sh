#!/usr/bin/env bash
# Railway Web Service Start Script
set -o errexit

echo "=== Running database migrations ==="
python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant

echo "=== Setting up public tenant ==="
python manage.py setup_public_tenant || echo "Public tenant already exists"

echo "=== Creating superuser if not exists ==="
if [ -n "$SUPERUSER_USERNAME" ] && [ -n "$SUPERUSER_EMAIL" ] && [ -n "$SUPERUSER_PASSWORD" ]; then
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$SUPERUSER_USERNAME', '$SUPERUSER_EMAIL', '$SUPERUSER_PASSWORD')
    print('Superuser created successfully')
else:
    print('Superuser already exists')
" || echo "Failed to create superuser"
else
    echo "Superuser env vars not set, skipping"
fi

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
