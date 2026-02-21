# Logging Configuration for Hybrid Architecture

## Add to settings.py

\\\python
import os

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {module} '
                     'container_type={container_type} '
                     '{message}',
            'style': '{',
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s '
                     '%(container_type)s %(pathname)s %(lineno)d'
        },
    },
    'filters': {
        'add_container_info': {
            '()': 'common.logging_filters.ContainerInfoFilter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'filters': ['add_container_info'],
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',  # Set to DEBUG to see SQL queries
            'propagate': False,
        },
        'channels': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
\\\

## Create Logging Filter

Create \common/logging_filters.py\:

\\\python
import logging
import os
from django.conf import settings

class ContainerInfoFilter(logging.Filter):
    '''Add container type and name to log records'''
    
    def filter(self, record):
        record.container_type = getattr(settings, 'CONTAINER_TYPE', 'unknown')
        record.container_name = os.environ.get('HOSTNAME', 'local')
        return True
\\\

## Metrics to Track

### WSGI Containers
- Request count per endpoint
- Response time (P50, P95, P99)
- Error rate (4xx, 5xx)
- Database query count
- Cache hit rate
- CPU and memory usage

### ASGI Containers
- Active WebSocket connections
- Streaming request duration
- Concurrent requests
- Channels layer message count
- Event loop lag
- CPU and memory usage

## Monitoring Stack (Recommended)

1. **Prometheus** - Metrics collection
2. **Grafana** - Dashboards
3. **Loki** - Log aggregation
4. **Tempo** - Distributed tracing (optional)

## Example Log Output

### WSGI Container
\\\
[INFO] 2026-02-05 12:17:00 django.request container_type=wsgi GET /api/models/ 200
\\\

### ASGI Container
\\\
[INFO] 2026-02-05 12:17:05 channels container_type=asgi WebSocket connected session_abc123
\\\

## Alerts to Configure

| Metric | Threshold | Action |
|--------|-----------|--------|
| Error rate | > 5% | Alert team |
| P95 latency | > baseline + 50% | Investigate |
| Container restarts | > 3 in 10 min | Alert team |
| Memory usage | > 85% | Scale or investigate |
| Active connections (ASGI) | > 180 per container | Scale up |

