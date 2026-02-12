# Health Check Implementation
# Add to common/views.py

from django.http import JsonResponse
from django.conf import settings
from django.db import connection
from django.core.cache import cache
import os

def health_check(request):
    '''
    Health check endpoint that returns container type and status
    '''
    container_type = getattr(settings, 'CONTAINER_TYPE', 'unknown')
    async_enabled = getattr(settings, 'USE_ASYNC_VIEWS', False)
    
    health_data = {
        'status': 'healthy',
        'container_type': container_type,
        'async_enabled': async_enabled,
        'version': '1.0.0',
        'checks': {}
    }
    
    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        health_data['checks']['database'] = 'ok'
    except Exception as e:
        health_data['checks']['database'] = 'failed'
        health_data['status'] = 'unhealthy'
    
    # Cache check
    try:
        cache.set('health_check_test', 'ok', 10)
        if cache.get('health_check_test') == 'ok':
            health_data['checks']['cache'] = 'ok'
        else:
            health_data['checks']['cache'] = 'failed'
    except Exception as e:
        health_data['checks']['cache'] = 'failed'
    
    # Channels check (for ASGI)
    if container_type == 'asgi':
        try:
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            health_data['checks']['channels'] = 'configured'
        except Exception as e:
            health_data['checks']['channels'] = 'failed'
    
    status_code = 200 if health_data['status'] == 'healthy' else 503
    return JsonResponse(health_data, status=status_code)
