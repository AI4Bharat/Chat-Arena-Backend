# Health Check URL Configuration
# Add to your main urls.py or common/urls.py

from django.urls import path
from common.views import health_check

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('api/health/', health_check, name='api_health_check'),
]
