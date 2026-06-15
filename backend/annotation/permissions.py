# backend/annotation/permissions.py

from rest_framework import permissions


class IsAssignedAnnotator(permissions.BasePermission):
    """
    Grants access only when the requesting user is in the session's
    annotation_users M2M set.

    Expects the view to provide an object whose .message.session is a
    ChatSession instance, or a ChatSession directly.
    """

    def has_object_permission(self, request, view, obj):
        session = _resolve_session(obj)
        if session is None:
            return False
        return session.annotation_users.filter(id=request.user.id).exists()


class IsAssignedReviewer(permissions.BasePermission):
    """
    Grants access only when the requesting user is the session's review_user.
    """

    def has_object_permission(self, request, view, obj):
        session = _resolve_session(obj)
        if session is None:
            return False
        return session.review_user_id == request.user.id


class IsAssignedSuperChecker(permissions.BasePermission):
    """
    Grants access only when the requesting user is the session's
    super_check_user.
    """

    def has_object_permission(self, request, view, obj):
        session = _resolve_session(obj)
        if session is None:
            return False
        return session.super_check_user_id == request.user.id


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _resolve_session(obj):
    """
    Resolves a ChatSession from an OCRAnnotation or ChatSession instance.
    Returns None if resolution is not possible.
    """
    from chat_session.models import ChatSession  # local import to avoid circular

    if isinstance(obj, ChatSession):
        return obj
    # OCRAnnotation → message → session
    if hasattr(obj, "message"):
        return obj.message.session
    return None