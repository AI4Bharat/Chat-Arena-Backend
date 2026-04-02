from django.urls import path, include
from rest_framework.routers import DefaultRouter
from chat_session.views import ChatSessionViewSet, SharedChatSessionView

app_name = 'chat_session'

router = DefaultRouter()
router.register(r'sessions', ChatSessionViewSet, basename='session')
router.register(r'shared', SharedChatSessionView, basename='shared')

urlpatterns = [
    path('', include(router.urls)),
]

# URL patterns will be:
# GET /api/sessions/ - List user's sessions
# POST /api/sessions/ - Create new session
# GET /api/sessions/{id}/ - Get session details
# PATCH /api/sessions/{id}/ - Update session
# DELETE /api/sessions/{id}/ - Delete session
# POST /api/sessions/{id}/share/ - Share session
# POST /api/sessions/{id}/unshare/ - Unshare session
# POST /api/sessions/{id}/duplicate/ - Duplicate session
# GET /api/sessions/{id}/export/ - Export session
# GET /api/sessions/{id}/statistics/ - Get session statistics
# POST /api/sessions/{id}/transfer_ownership/ - Transfer ownership
# GET /api/sessions/shared/ - List public sessions
# GET /api/sessions/trending/ - Get trending sessions
# GET  /api/shared/{share_token}/          - View shared session (read-only, no auth required)
# POST /api/shared/{share_token}/continue/ - Fork shared session into caller's account (auth required)