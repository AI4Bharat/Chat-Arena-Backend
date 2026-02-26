"""Utility for logging general endpoint errors to GCS"""
from datetime import datetime
from rest_framework.response import Response
from rest_framework import status as http_status
import traceback
import logging

logger = logging.getLogger(__name__)


def categorize_error(exception):
    """
    Categorize exception into error types for better analysis.
    
    Args:
        exception: The caught exception
    
    Returns:
        str: Error category
    """
    from django.core.exceptions import ValidationError, ObjectDoesNotExist
    from django.db import DatabaseError, IntegrityError
    from rest_framework.exceptions import (
        PermissionDenied, NotAuthenticated, NotFound, 
        ValidationError as DRFValidationError
    )
    
    if isinstance(exception, (ValueError, TypeError, KeyError, ValidationError, DRFValidationError)):
        return 'validation_error'
    elif isinstance(exception, (DatabaseError, IntegrityError)):
        return 'database_error'
    elif isinstance(exception, (PermissionDenied, NotAuthenticated)):
        return 'permission_error'
    elif isinstance(exception, (ObjectDoesNotExist, NotFound)):
        return 'not_found_error'
    else:
        return 'server_error'


def extract_endpoint_error_details(exception, endpoint, log_context=None):
    """
    Extract structured error details from an endpoint exception.
    
    Args:
        exception: The caught exception
        endpoint: Endpoint identifier (e.g., '/sessions/', '/feedback/my_stats/')
        log_context: Optional dict with user_id, user_email, session_id, request details
    
    Returns:
        dict: Structured error log entry
    """
    log_context = log_context or {}
    
    error_entry = {
        'error_type': categorize_error(exception),
        'endpoint': endpoint,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'error_message': str(exception),
        'error_class': type(exception).__name__,
        'traceback': traceback.format_exc(),
        
        # User context
        'user_email': log_context.get('user_email'),
        'user_id': log_context.get('user_id'),
        
        # Request context
        'request_method': log_context.get('request_method'),
        'request_params': log_context.get('request_params'),
        'request_body': log_context.get('request_body'),
        
        # Session context (if applicable)
        'session_id': log_context.get('session_id'),
        
        # Response
        'status_code': log_context.get('status_code'),
    }
    
    return error_entry


def log_endpoint_error_to_gcs(error_entry):
    """
    Log endpoint error to GCS using the same pattern as frontend error logs.
    
    Args:
        error_entry: dict with error details
    """
    from frontend_logs.views import write_log_to_gcs
    
    # Add received_at timestamp
    error_entry['received_at'] = datetime.utcnow().isoformat() + 'Z'
    
    # Reuse existing GCS logging function
    try:
        write_log_to_gcs(error_entry)
    except Exception as e:
        # Don't fail the request if logging fails
        logger.error(f"Failed to log endpoint error to GCS: {e}")


def log_and_respond(exception, endpoint, log_context=None, status_code=None, custom_message=None):
    """
    Log error to GCS and return appropriate Response.
    
    Args:
        exception: The caught exception
        endpoint: Endpoint identifier
        log_context: Optional context dict
        status_code: HTTP status code for response (auto-determined if None)
        custom_message: Optional custom error message for user
    
    Returns:
        Response: DRF Response object with error message
    """
    # Determine status code if not provided
    if status_code is None:
        error_type = categorize_error(exception)
        status_code_map = {
            'validation_error': http_status.HTTP_400_BAD_REQUEST,
            'database_error': http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            'permission_error': http_status.HTTP_403_FORBIDDEN,
            'not_found_error': http_status.HTTP_404_NOT_FOUND,
            'server_error': http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        }
        status_code = status_code_map.get(error_type, http_status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Add status code to context
    if log_context is None:
        log_context = {}
    log_context['status_code'] = status_code
    
    # Extract and log error details
    error_details = extract_endpoint_error_details(exception, endpoint, log_context)
    
    try:
        log_endpoint_error_to_gcs(error_details)
    except Exception as log_err:
        # Don't fail the request if logging fails
        logger.error(f"Failed to log endpoint error: {log_err}")
    
    # Determine user-facing error message
    if custom_message:
        error_message = custom_message
    elif status_code == http_status.HTTP_400_BAD_REQUEST:
        error_message = f"Invalid request: {str(exception)}"
    elif status_code == http_status.HTTP_404_NOT_FOUND:
        error_message = "Resource not found"
    elif status_code == http_status.HTTP_403_FORBIDDEN:
        error_message = "Permission denied"
    else:
        error_message = "An unexpected error occurred. Please try again later."
    
    # Return error response
    return Response(
        {'error': error_message},
        status=status_code
    )


def create_log_context(request, session_id=None):
    """
    Helper function to create log context from request.
    
    Args:
        request: Django request object
        session_id: Optional session ID
    
    Returns:
        dict: Log context with user and request details
    """
    context = {
        'user_email': getattr(request.user, 'email', None) if hasattr(request, 'user') else None,
        'user_id': str(request.user.id) if hasattr(request, 'user') and request.user and hasattr(request.user, 'id') else None,
        'request_method': request.method if hasattr(request, 'method') else None,
        'request_params': dict(request.query_params) if hasattr(request, 'query_params') else {},
    }
    
    # Add request body for non-GET requests (be careful with sensitive data)
    if hasattr(request, 'data') and request.method != 'GET':
        # Filter out sensitive fields
        safe_data = {k: v for k, v in request.data.items() if k not in ['password', 'token', 'api_key']}
        context['request_body'] = safe_data
    
    if session_id:
        context['session_id'] = str(session_id)
    
    return context
