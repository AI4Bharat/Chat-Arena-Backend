"""
Health check endpoints for load balancer and monitoring.

These endpoints are used by:
- Nginx upstream health checks
- Kubernetes liveness/readiness probes
- External monitoring systems
"""
import logging
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
from django.conf import settings
import time

logger = logging.getLogger(__name__)


def health(request):
    """
    Basic health check endpoint.

    Returns 200 OK if the service is running.
    Used by load balancers for basic connectivity checks.
    """
    return JsonResponse({
        'status': 'healthy',
        'service': 'arena-backend',
        'timestamp': time.time()
    }, status=200)


def liveness(request):
    """
    Liveness probe endpoint.

    Checks if the application process is alive and responsive.
    If this fails, the container should be restarted.

    Returns:
        200 OK: Application is alive
        500 Error: Application is deadlocked or unresponsive
    """
    try:
        # Simple check - if we can respond, we're alive
        return JsonResponse({
            'status': 'alive',
            'timestamp': time.time()
        }, status=200)
    except Exception as e:
        logger.error(f"Liveness check failed: {str(e)}")
        return JsonResponse({
            'status': 'dead',
            'error': str(e),
            'timestamp': time.time()
        }, status=500)


def readiness(request):
    """
    Readiness probe endpoint.

    Checks if the application is ready to serve traffic.
    Tests critical dependencies:
    - Database connectivity
    - Redis cache connectivity

    Returns:
        200 OK: Application is ready to serve traffic
        503 Service Unavailable: Application is not ready (still starting or dependencies down)
    """
    checks = {}
    all_ready = True

    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'failed: {str(e)}'
        all_ready = False
        logger.error(f"Database readiness check failed: {str(e)}")

    # Check Redis cache connectivity
    try:
        cache.set('health_check', 'ok', timeout=10)
        result = cache.get('health_check')
        if result == 'ok':
            checks['cache'] = 'ok'
        else:
            checks['cache'] = 'failed: cache read/write mismatch'
            all_ready = False
    except Exception as e:
        checks['cache'] = f'failed: {str(e)}'
        all_ready = False
        logger.error(f"Cache readiness check failed: {str(e)}")

    status_code = 200 if all_ready else 503
    response_data = {
        'status': 'ready' if all_ready else 'not_ready',
        'checks': checks,
        'timestamp': time.time()
    }

    return JsonResponse(response_data, status=status_code)


def detailed_status(request):
    """
    Detailed status endpoint for monitoring and debugging.

    Provides comprehensive information about the application state:
    - Python version
    - Django version
    - Database status
    - Cache status
    - Configuration summary

    Should be used by monitoring dashboards, not load balancers.
    """
    import sys
    import django

    checks = {}

    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            db_version = cursor.fetchone()[0]
        checks['database'] = {
            'status': 'connected',
            'engine': settings.DATABASES['default']['ENGINE'],
            'name': settings.DATABASES['default']['NAME'],
            'host': settings.DATABASES['default'].get('HOST', 'localhost'),
            'version': db_version
        }
    except Exception as e:
        checks['database'] = {
            'status': 'error',
            'error': str(e)
        }

    # Cache check
    try:
        cache.set('status_check', 'test', timeout=10)
        result = cache.get('status_check')
        checks['cache'] = {
            'status': 'connected' if result == 'test' else 'error',
            'backend': settings.CACHES['default']['BACKEND'],
            'location': settings.CACHES['default']['LOCATION']
        }
    except Exception as e:
        checks['cache'] = {
            'status': 'error',
            'error': str(e)
        }

    return JsonResponse({
        'status': 'operational',
        'service': 'arena-backend',
        'python_version': sys.version,
        'django_version': django.get_version(),
        'debug_mode': settings.DEBUG,
        'checks': checks,
        'timestamp': time.time()
    }, status=200)
