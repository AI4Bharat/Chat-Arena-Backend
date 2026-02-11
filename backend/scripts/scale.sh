#!/bin/bash
# Scaling Script
# File: scripts/scale.sh

set -e

SERVICE=\
REPLICAS=\

if [ -z "\" ] || [ -z "\" ]; then
    echo "Usage: ./scripts/scale.sh [wsgi|asgi] [replicas]"
    echo ""
    echo "Examples:"
    echo "  ./scripts/scale.sh wsgi 4    # Scale WSGI to 4 containers"
    echo "  ./scripts/scale.sh asgi 3    # Scale ASGI to 3 containers"
    exit 1
fi

case \ in
    wsgi)
        echo "Scaling WSGI backend to \ replicas..."
        docker-compose -f docker-compose.hybrid.yml up -d --scale backend-wsgi=\ --no-recreate
        ;;
    asgi)
        echo "Scaling ASGI backend to \ replicas..."
        docker-compose -f docker-compose.hybrid.yml up -d --scale backend-asgi=\ --no-recreate
        ;;
    *)
        echo "Invalid service: \"
        echo "Must be 'wsgi' or 'asgi'"
        exit 1
        ;;
esac

echo "✅ Scaling complete"
echo ""
echo "Current status:"
docker-compose -f docker-compose.hybrid.yml ps | grep backend
