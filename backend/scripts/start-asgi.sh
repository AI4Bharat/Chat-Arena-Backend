#!/bin/bash
# Start ASGI server with Uvicorn
# File: scripts/start-asgi.sh

set -e

echo "Starting Arena Backend ASGI server..."

# Wait for database
echo "Waiting for database..."
while ! nc -z \ \; do
  sleep 0.1
done
echo "Database is ready"

# Wait for Redis
echo "Waiting for Redis..."
while ! nc -z \ \; do
  sleep 0.1
done
echo "Redis is ready"

# Start Uvicorn
echo "Starting Uvicorn..."
exec uvicorn arena_backend.asgi:application \
    --host 0.0.0.0 \
    --port 8001 \
    --workers \ \
    --loop uvloop \
    --log-level \ \
    --access-log \
    --timeout-keep-alive 5
