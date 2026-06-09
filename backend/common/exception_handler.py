"""
Custom DRF exception handler that prevents API key leakage in error responses.
"""
import logging
from rest_framework.views import exception_handler
from django.conf import settings

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler for Django REST Framework.

    In production (DEBUG=False):
    - Standard DRF exceptions (400, 401, 403, 404, etc.) are handled normally
    - Unhandled exceptions return a generic error message without exposing internals

    In development (DEBUG=True):
    - Falls through to Django's default debug error pages
    """
    # Let DRF handle its own exceptions (validation errors, auth errors, etc.)
    response = exception_handler(exc, context)

    if response is not None:
        # Standard DRF exception — safe to return as-is
        return response

    # Unhandled exception (would be a 500)
    # Log the full error server-side
    view = context.get('view', None)
    view_name = view.__class__.__name__ if view else 'Unknown'
    logger.error(
        f"Unhandled exception in {view_name}: {exc}",
        exc_info=True,
        extra={'view': view_name}
    )

    if not getattr(settings, 'DEBUG', False):
        # In production, return a generic error without leaking internals
        from rest_framework.response import Response
        from rest_framework import status

        return Response(
            {'error': 'An internal server error occurred. Please try again later.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # In development, return None to let Django show its debug page
    return None
