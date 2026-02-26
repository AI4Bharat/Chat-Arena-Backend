#!/bin/bash
# Quick Start Script for Local Development
# File: scripts/quick-start.sh

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         Chat-Arena-Backend Quick Start                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Setup environment
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "✅ .env created. Please update with your settings."
    echo ""
fi

# Start Redis
echo "Starting Redis..."
docker run -d -p 6379:6379 --name redis-local redis:7-alpine || docker start redis-local
echo "✅ Redis running"

# Start PostgreSQL (if not running)
if ! docker ps | grep -q postgres-local; then
    echo "Starting PostgreSQL..."
    docker run -d \
        --name postgres-local \
        -e POSTGRES_DB=arena_dev \
        -e POSTGRES_USER=arena_user \
        -e POSTGRES_PASSWORD=dev_password \
        -p 5432:5432 \
        postgres:17-alpine
    
    echo "Waiting for PostgreSQL to start..."
    sleep 5
fi
echo "✅ PostgreSQL running"

# Run migrations
echo "Running migrations..."
python manage.py migrate
echo "✅ Migrations complete"

# Create superuser (optional)
echo ""
echo "Create superuser? (y/n)"
read -r response
if [ "\y" = "y" ]; then
    python manage.py createsuperuser
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                   Ready to Start! 🚀                            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Start WSGI server:"
echo "  python manage.py runserver"
echo ""
echo "Start ASGI server:"
echo "  export CONTAINER_TYPE=asgi"
echo "  export USE_ASYNC_VIEWS=True"
echo "  uvicorn arena_backend.asgi:application --port 8001 --reload"
echo ""
