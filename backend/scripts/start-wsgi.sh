#!/bin/bash
# Start WSGI server with Gunicorn
# File: scripts/start-wsgi.sh

set -e

echo "Starting Arena Backend WSGI server..."

# Wait for database
echo "Waiting for database..."
while ! nc -z \ \; do
  sleep 0.1
done
echo "Database is ready"

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Start Gunicorn
echo "Starting Gunicorn..."
exec gunicorn arena_backend.wsgi:application \
    --config config/gunicorn.conf.py \
    --bind 0.0.0.0:8000
