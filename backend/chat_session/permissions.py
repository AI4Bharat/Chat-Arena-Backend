from rest_framework import permissions


class IsSessionOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of a session to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions for public sessions
        if request.method in permissions.SAFE_METHODS and obj.is_public:
            return True
        
        # Write permissions are only allowed to the owner
        return obj.user == request.user


class CanAccessSharedSession(permissions.BasePermission):
    """
    Permission for accessing shared sessions via share token
    """
    def has_object_permission(self, request, view, obj):
        # Allow if session is public
        if obj.deleted_at is not None:
            return False

        # Allow if session is public
        if obj.is_public:
            return True

        # Fallback: check raw share token from URL or query param
        share_token = view.kwargs.get('share_token') or request.query_params.get('share_token')
        return bool(share_token and obj.share_token == share_token)