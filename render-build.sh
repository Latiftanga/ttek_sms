#!/usr/bin/env bash
# Render Build Script
# This script runs during the build phase on Render

set -o errexit  # Exit on error

echo "=== Installing Python dependencies ==="
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Building Tailwind CSS ==="
python manage.py tailwind build

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput

echo "=== Build complete ==="
