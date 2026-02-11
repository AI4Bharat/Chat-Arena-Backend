"""
URL Configuration for Async Views
Add to message/urls.py or create message/urls_async.py
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.conf import settings

# Import async views
from message.views_async import MessageViewSetAsync, stream_message_simple

app_name = 'message'

# ============================================================================
# CONDITIONAL ROUTING BASED ON CONTAINER TYPE
# ============================================================================

if getattr(settings, 'CONTAINER_TYPE', 'wsgi') == 'asgi' and getattr(settings, 'USE_ASYNC_VIEWS', False):
    # ASGI MODE: Use async views for streaming
    print("🚀 Using ASYNC views for message streaming")
    
    router = DefaultRouter()
    router.register(r'messages', MessageViewSetAsync, basename='message')
    
    urlpatterns = [
        path('', include(router.urls)),
        
        # Alternative simple endpoint
        path('messages/stream-simple/', stream_message_simple, name='stream-simple'),
    ]

else:
    # WSGI MODE: Use sync views
    print("📦 Using SYNC views for messages")
    
    from message.views import MessageViewSet
    
    router = DefaultRouter()
    router.register(r'messages', MessageViewSet, basename='message')
    
    urlpatterns = [
        path('', include(router.urls)),
    ]

# Additional endpoints (transliteration, transcription)
from message.views import TransliterationAPIView, TranscribeAPIView

urlpatterns += [
    path(
        "xlit-api/generic/transliteration/<str:target_language>/<str:data>",
        TransliterationAPIView.as_view(),
        name="transliteration-api",
    ),
    path(
        "asr-api/generic/transcribe",
        TranscribeAPIView.as_view(),
        name="transcription-api",
    ),
]
