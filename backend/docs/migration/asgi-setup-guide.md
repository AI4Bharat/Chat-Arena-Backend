# ASGI Setup and Troubleshooting Guide

## Architecture Overview

The Chat-Arena-Backend uses Django Channels for ASGI support, enabling:
- Asynchronous HTTP request handling
- WebSocket connections for real-time chat
- Concurrent external API calls (OpenAI, Anthropic, etc.)

## ASGI Entry Point

**File:** \rena_backend/asgi.py\

### Configuration
\\\python
application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
\\\

**Protocols:**
- \http\: Regular HTTP requests
- \websocket\: WebSocket connections

**WebSocket Routes:**
- \ws://domain/ws/chat/session/<session_id>/\

## Running ASGI Locally

### Development Mode (Windows)
\\\powershell
# Set environment
\wsgi="asgi"
\="True"

# Start Uvicorn
uvicorn arena_backend.asgi:application --host 0.0.0.0 --port 8001 --reload
\\\

### Production Mode (Linux)
\\\ash
# Option 1: Uvicorn
uvicorn arena_backend.asgi:application \\
    --host 0.0.0.0 \\
    --port 8001 \\
    --workers 2 \\
    --loop uvloop

# Option 2: Daphne
daphne -b 0.0.0.0 -p 8001 \\
    --access-log - \\
    arena_backend.asgi:application
\\\

## Verifying ASGI

### Test HTTP Endpoint
\\\ash
curl http://localhost:8001/api/health/
\\\

Expected response:
\\\json
{
  "status": "healthy",
  "container_type": "asgi",
  "async_enabled": true,
  "checks": {
    "database": "ok",
    "cache": "ok",
    "channels": "configured"
  }
}
\\\

### Test WebSocket Connection
\\\javascript
// In browser console
const ws = new WebSocket('ws://localhost:8001/ws/chat/session/test123/');
ws.onopen = () => console.log('Connected');
ws.onmessage = (e) => console.log('Message:', e.data);
ws.send(JSON.stringify({type: 'test', message: 'Hello'}));
\\\

## Common Issues

### 1. Redis Connection Error
**Error:** \ConnectionRefusedError: [Errno 111] Connection refused\

**Solution:**
\\\ash
# Start Redis
docker run -d -p 6379:6379 --name redis-local redis:7-alpine

# Verify
redis-cli ping
\\\

### 2. Channels Layer Not Configured
**Error:** \RuntimeError: No channel layer configured\

**Solution:** Check \settings.py\:
\\\python
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('127.0.0.1', 6379)],
        },
    },
}
\\\

### 3. WebSocket Forbidden (403)
**Error:** \WebSocket connection failed: Error during WebSocket handshake: Unexpected response code: 403\

**Cause:** \AllowedHostsOriginValidator\ blocking request

**Solution:** Add to \ALLOWED_HOSTS\ in settings:
\\\python
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'your-domain.com']
\\\

### 4. Import Error: ChatSessionConsumer
**Error:** \ImportError: cannot import name 'ChatSessionConsumer'\

**Solution:** Verify consumer exists in \chat_session/consumers.py\

### 5. Database Query in Async Context
**Error:** \SynchronousOnlyOperation: You cannot call this from an async context\

**Solution:** Wrap ORM queries:
\\\python
from asgiref.sync import sync_to_async

@sync_to_async
def get_session(session_id):
    return ChatSession.objects.get(id=session_id)

# In async function
session = await get_session(session_id)
\\\

## Performance Tuning

### Uvicorn Workers
\\\ash
# Single worker (development)
uvicorn app:application --workers 1

# Multiple workers (production)
# Workers = (2 x CPU cores) or (CPU cores + 1)
uvicorn app:application --workers 2
\\\

### Connection Limits
\\\ash
uvicorn app:application --limit-concurrency 200 --limit-max-requests 1000
\\\

### uvloop (Linux only - performance boost)
\\\ash
pip install uvloop
uvicorn app:application --loop uvloop
\\\

## Monitoring ASGI

### Key Metrics
- Active WebSocket connections: \/admin/channels/\ (if available)
- Memory usage: Should be stable, not growing
- Event loop lag: Should be < 50ms
- Request latency: Streaming should start quickly

### Logs to Watch
\\\ash
# Docker
docker logs -f backend-asgi-1

# Systemd
journalctl -u arena-asgi -f
\\\

## Deployment Checklist

- [ ] Redis is running and accessible
- [ ] \CHANNEL_LAYERS\ configured in settings
- [ ] \ASGI_APPLICATION\ setting points to correct app
- [ ] WebSocket routes defined
- [ ] \ALLOWED_HOSTS\ includes all domains
- [ ] Nginx configured for WebSocket upgrade
- [ ] Health check endpoint returns 200
- [ ] Test WebSocket connection works
- [ ] Monitor logs for errors

## Next Steps After Setup

1. Test streaming endpoint (\/api/messages/stream/\)
2. Test WebSocket chat
3. Monitor resource usage
4. Load test with concurrent connections
5. Configure alerts and monitoring

## Resources

- **Django Channels:** https://channels.readthedocs.io/
- **Uvicorn:** https://www.uvicorn.org/
- **Daphne:** https://github.com/django/daphne
- **Redis:** https://redis.io/docs/

