# Environment Configuration Guide

## Overview

The hybrid architecture uses environment variables to configure container behavior.

## Container Types

### WSGI Containers
- Handle synchronous CRUD operations
- Environment: \.env.wsgi.example\
- Key settings:
  - \CONTAINER_TYPE=wsgi\
  - \USE_ASYNC_VIEWS=False\

### ASGI Containers
- Handle asynchronous streaming and WebSocket
- Environment: \.env.asgi.example\
- Key settings:
  - \CONTAINER_TYPE=asgi\
  - \USE_ASYNC_VIEWS=True\

## Environment Variables

| Variable | WSGI Value | ASGI Value | Description |
|----------|------------|------------|-------------|
| CONTAINER_TYPE | wsgi | asgi | Container identification |
| USE_ASYNC_VIEWS | False | True | Enable async view routing |
| DB_POOL_SIZE | 20 | 10 | Database connections per container |
| REDIS_MAX_CONNECTIONS | 50 | 100 | Redis connection pool size |

## Local Development

For local development, use the current \.env\ file with:
\\\
CONTAINER_TYPE=wsgi
USE_ASYNC_VIEWS=False
DEBUG=True
\\\

## Production Deployment

1. Copy appropriate example file:
   \\\ash
   cp .env.wsgi.example .env.wsgi
   cp .env.asgi.example .env.asgi
   \\\

2. Update with production values

3. Mount in Docker Compose:
   \\\yaml
   backend-wsgi:
     env_file: .env.wsgi
   
   backend-asgi:
     env_file: .env.asgi
   \\\

## Security Notes

- Never commit actual \.env\ files to git
- Use secrets management in production
- Rotate SECRET_KEY regularly
- Use strong database passwords
