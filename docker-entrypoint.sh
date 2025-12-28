#!/bin/sh
set -e

echo "=== Waiting for database ==="
python manage.py wait_for_db  # You'll need to create this command

echo "=== Running migrations for shared schema ==="
python manage.py migrate_schemas --shared

echo "=== Running migrations for tenant schemas ==="
python manage.py migrate_schemas --tenant

echo "=== Starting application ==="
exec "$@"