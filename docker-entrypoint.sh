#!/bin/sh
set -e

echo "⏳ Waiting for database..."
python manage.py wait_for_db

echo "📦 Running migrations for shared schema..."
python manage.py migrate_schemas --shared

echo "🏫 Setting up public tenant (required for django-tenants)..."
python manage.py setup_public_tenant

echo "📦 Running migrations for tenant schemas..."
python manage.py migrate_schemas --tenant

# Only collect static files in production (when DEBUG is not true)
# In development, Django's runserver serves static files directly
if [ "$DEBUG" != "True" ] && [ "$DEBUG" != "true" ]; then
    echo "📁 Collecting static files..."
    python manage.py collectstatic --noinput
else
    echo "📁 Skipping collectstatic (DEBUG mode)"
fi

echo "🚀 Starting application..."
exec "$@"