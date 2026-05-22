"""
Tests for common.exception_handler — custom_exception_handler().

Verifies that:
- Standard DRF exceptions pass through normally.
- Unhandled exceptions return a generic 500 in production (DEBUG=False).
- Unhandled exceptions return None in development (DEBUG=True).
"""
from unittest.mock import MagicMock, patch
from django.test import TestCase, override_settings
from rest_framework.exceptions import NotFound, ValidationError
from common.exception_handler import custom_exception_handler


class CustomExceptionHandlerTests(TestCase):
    """Test custom DRF exception handler."""

    def _make_context(self, view_name='TestView'):
        """Create a minimal DRF context dict."""
        view = MagicMock()
        view.__class__.__name__ = view_name
        return {'view': view, 'request': MagicMock()}

    # ── Standard DRF exceptions ────────────────────────────────────
    def test_handles_drf_not_found(self):
        """Standard 404 should pass through with normal DRF response."""
        exc = NotFound("Resource not found")
        context = self._make_context()
        response = custom_exception_handler(exc, context)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 404)

    def test_handles_drf_validation_error(self):
        """Validation errors should pass through normally."""
        exc = ValidationError({"field": ["This field is required."]})
        context = self._make_context()
        response = custom_exception_handler(exc, context)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 400)

    # ── Unhandled exceptions in production ─────────────────────────
    @override_settings(DEBUG=False)
    def test_unhandled_exception_returns_generic_500_in_production(self):
        """In production, unhandled exceptions return generic error, no internals."""
        exc = RuntimeError("Database connection pool exhausted: password=secret123")
        context = self._make_context()
        response = custom_exception_handler(exc, context)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 500)
        self.assertIn('error', response.data)
        # Must NOT leak the actual error message
        self.assertNotIn('secret123', str(response.data))
        self.assertNotIn('Database connection', str(response.data))

    # ── Unhandled exceptions in development ────────────────────────
    @override_settings(DEBUG=True)
    def test_unhandled_exception_returns_none_in_debug(self):
        """In development, return None so Django shows its debug page."""
        exc = RuntimeError("Some debug error")
        context = self._make_context()
        response = custom_exception_handler(exc, context)
        self.assertIsNone(response)
