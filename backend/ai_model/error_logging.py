"""Utility for logging AI model errors to GCS"""
from datetime import datetime
import json


def extract_error_details(exception, model_code, provider, context=None):
    """
    Extract structured error details from an exception.
    
    Args:
        exception: The caught exception
        model_code: Model identifier (e.g., 'gpt-4o', 'gemini-1.5-pro')
        provider: Provider name (e.g., 'openai', 'google', 'dhruva')
        context: Optional dict with session_id, message_id, user_email
    
    Returns:
        dict: Structured error log entry
    """
    context = context or {}
    
    error_entry = {
        'error_type': 'model_error',
        'model': model_code,
        'provider': provider,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'error_message': str(exception),
        'session_id': context.get('session_id'),
        'message_id': context.get('message_id'),
        'user_email': context.get('user_email'),
    }
    
    # Extract HTTP response details if available
    if hasattr(exception, 'response'):
        response = exception.response
        error_entry['status_code'] = getattr(response, 'status_code', None)
        
        # Try to get request ID from headers
        if hasattr(response, 'headers'):
            headers = response.headers
            error_entry['request_id'] = headers.get('x-request-id') or headers.get('X-Request-Id')
        
        # Try to parse JSON error body
        try:
            if hasattr(response, 'json') and callable(response.json):
                error_entry['response_body'] = response.json()
            elif hasattr(response, 'text'):
                error_entry['response_body'] = response.text
        except Exception:
            pass
    
    # Extract request details if available
    if hasattr(exception, 'request'):
        request = exception.request
        # Convert URL object to string for JSON serialization
        url = getattr(request, 'url', None)
        error_entry['request_url'] = str(url) if url is not None else None
        error_entry['request_method'] = getattr(request, 'method', None)
    
    return error_entry


def log_model_error_to_gcs(error_entry):
    """
    Log model error to GCS using the same pattern as frontend error logs.
    
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
        print(f"Failed to log model error to GCS: {e}")


def log_and_raise(exception, model_code, provider, context=None, custom_message=None):
    """
    Log error to GCS and re-raise with custom message.
    
    Args:
        exception: The caught exception
        model_code: Model identifier
        provider: Provider name
        context: Optional context dict
        custom_message: Optional custom error message to raise
    
    Raises:
        Exception: Re-raises with custom or original message
    """
    # Extract and log error details
    error_details = extract_error_details(exception, model_code, provider, context)
    
    try:
        log_model_error_to_gcs(error_details)
    except Exception as log_err:
        # Don't fail the request if logging fails
        print(f"Failed to log model error: {log_err}")
    
    # Re-raise with custom message or original
    if custom_message:
        raise Exception(custom_message)
    else:
        raise exception
