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

echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

echo "🚀 Starting application..."
exec "$@"