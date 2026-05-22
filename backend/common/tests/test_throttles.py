"""
Tests for common.throttles — AIGenerationThrottle and AuthRateThrottle.

Verifies that throttle classes have the correct scope and correct base class.
"""
from django.test import TestCase
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from common.throttles import AIGenerationThrottle, AuthRateThrottle


class AIGenerationThrottleTests(TestCase):
    """Test AIGenerationThrottle configuration."""

    def test_scope_is_ai_generation(self):
        self.assertEqual(AIGenerationThrottle.scope, 'ai_generation')

    def test_is_user_rate_throttle(self):
        self.assertTrue(issubclass(AIGenerationThrottle, UserRateThrottle))


class AuthRateThrottleTests(TestCase):
    """Test AuthRateThrottle configuration."""

    def test_scope_is_auth(self):
        self.assertEqual(AuthRateThrottle.scope, 'auth')

    def test_is_anon_rate_throttle(self):
        self.assertTrue(issubclass(AuthRateThrottle, AnonRateThrottle))
