"""
Tests for Django settings security configuration.

Verifies that:
- CORS is locked down (not wildcard).
- Throttle classes and rates are configured.
- All required throttle scopes exist.
"""
from django.test import TestCase
from django.conf import settings


class CORSSettingsTests(TestCase):
    """Test CORS configuration is secure."""

    def test_cors_origin_allow_all_is_false(self):
        """CORS must NOT allow all origins."""
        self.assertFalse(
            getattr(settings, 'CORS_ORIGIN_ALLOW_ALL', True),
            "CORS_ORIGIN_ALLOW_ALL must be False in production"
        )

    def test_cors_allowed_origins_is_not_empty(self):
        """At least one trusted origin must be configured."""
        origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
        self.assertGreater(len(origins), 0, "CORS_ALLOWED_ORIGINS should not be empty")


class ThrottleSettingsTests(TestCase):
    """Test rate limiting configuration in REST_FRAMEWORK settings."""

    def setUp(self):
        self.rf = getattr(settings, 'REST_FRAMEWORK', {})

    def test_default_throttle_classes_exist(self):
        """DEFAULT_THROTTLE_CLASSES must be configured."""
        classes = self.rf.get('DEFAULT_THROTTLE_CLASSES', [])
        self.assertGreater(len(classes), 0, "DEFAULT_THROTTLE_CLASSES should not be empty")

    def test_anon_throttle_class_present(self):
        classes = self.rf.get('DEFAULT_THROTTLE_CLASSES', [])
        self.assertIn('rest_framework.throttling.AnonRateThrottle', classes)

    def test_user_throttle_class_present(self):
        classes = self.rf.get('DEFAULT_THROTTLE_CLASSES', [])
        self.assertIn('rest_framework.throttling.UserRateThrottle', classes)

    def test_throttle_rates_configured(self):
        """DEFAULT_THROTTLE_RATES must have all required scopes."""
        rates = self.rf.get('DEFAULT_THROTTLE_RATES', {})
        required_scopes = ['anon', 'user', 'ai_generation', 'auth', 'expensive_ai']
        for scope in required_scopes:
            self.assertIn(scope, rates, f"Missing throttle rate scope: '{scope}'")

    def test_anon_rate_is_not_unlimited(self):
        rates = self.rf.get('DEFAULT_THROTTLE_RATES', {})
        anon_rate = rates.get('anon', '')
        self.assertNotEqual(anon_rate, '', "Anon rate should not be empty")
        # Should contain a number and time unit
        self.assertRegex(anon_rate, r'\d+/\w+', "Anon rate should be in format 'N/period'")

    def test_user_rate_is_not_unlimited(self):
        rates = self.rf.get('DEFAULT_THROTTLE_RATES', {})
        user_rate = rates.get('user', '')
        self.assertNotEqual(user_rate, '', "User rate should not be empty")


class SecuritySettingsTests(TestCase):
    """Test other security-related Django settings."""

    def test_secret_key_is_set(self):
        """SECRET_KEY must be set (even if it's the dev fallback)."""
        self.assertTrue(hasattr(settings, 'SECRET_KEY'))
        self.assertGreater(len(settings.SECRET_KEY), 20, "SECRET_KEY is suspiciously short")

    def test_exception_handler_is_custom(self):
        """REST_FRAMEWORK should use the custom exception handler."""
        rf = getattr(settings, 'REST_FRAMEWORK', {})
        handler = rf.get('EXCEPTION_HANDLER', '')
        self.assertEqual(handler, 'common.exception_handler.custom_exception_handler')
