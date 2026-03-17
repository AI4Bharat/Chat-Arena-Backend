from rest_framework import permissions
from django.conf import settings
from chat_session.models import ChatSession


class HasAdminApiKey(permissions.BasePermission):
    """
    Checks for a static API key in the X-Admin-Api-Key request header.
    Key is configured via the ADMIN_API_KEY environment variable.
    """
    def has_permission(self, request, view):
        expected = settings.ADMIN_API_KEY
        if not expected:
            return False
        return request.headers.get('X-Admin-Api-Key') == expected


class IsFeedbackOwner(permissions.BasePermission):
    """
    Permission to only allow owners of feedback to edit it
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions for feedback on public sessions
        if request.method in permissions.SAFE_METHODS and obj.session.is_public:
            return True
        
        # Write permissions only for feedback owner
        return obj.user == request.user


class CanProvideFeedback(permissions.BasePermission):
    """
    Permission to check if user can provide feedback on a session
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        session_id = request.data.get('session_id')
        if not session_id:
            return True  # Will be validated in serializer
        
        try:
            session = ChatSession.objects.get(id=session_id)
            return session.user == request.user or session.is_public
        except ChatSession.DoesNotExist:
            return False