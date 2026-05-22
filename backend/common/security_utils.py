"""
Security utilities for sanitizing error messages and preventing API key exposure.
"""
import re


# Patterns that match common API key/secret formats
_SENSITIVE_PATTERNS = [
    # Bearer tokens
    (re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE), 'Bearer ***REDACTED***'),
    # OpenAI-style keys (sk-...)
    (re.compile(r'sk-[A-Za-z0-9_\-]{20,}'), 'sk-***REDACTED***'),
    # Azure-style keys (hex, 32+ chars)
    (re.compile(r'[0-9a-f]{32,}', re.IGNORECASE), '***REDACTED_HEX***'),
    # Generic long base64-ish tokens (40+ chars of alphanumeric + symbols)
    (re.compile(r'[A-Za-z0-9+/=_\-]{40,}'), '***REDACTED_TOKEN***'),
    # API key in URL query params (?key=... or &key=...)
    (re.compile(r'([?&])(key|api_key|apikey|token|secret|password)=([^&\s]+)', re.IGNORECASE),
     r'\1\2=***REDACTED***'),
]


def sanitize_error_message(exception):
    """
    Sanitize an exception message by redacting potential API keys and secrets.

    Use this instead of str(e) when the error message will be:
    - Returned in an HTTP response
    - Streamed to the client
    - Stored in client-visible logs

    Args:
        exception: An Exception instance or string

    Returns:
        str: Sanitized error message with sensitive values redacted
    """
    message = str(exception)

    # Apply URL query param pattern first (it's more specific)
    pattern, replacement = _SENSITIVE_PATTERNS[-1]
    message = pattern.sub(replacement, message)

    # Apply other patterns
    for pattern, replacement in _SENSITIVE_PATTERNS[:-1]:
        message = pattern.sub(replacement, message)

    return message
