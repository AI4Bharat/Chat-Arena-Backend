"""
Custom DRF throttle classes for rate limiting.

Scopes:
  - 'ai_generation': limits AI model generation requests (streaming endpoints)
  - 'auth': limits authentication attempts (login, register)
  - 'anon_burst': limits anonymous burst requests
"""
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class AIGenerationThrottle(UserRateThrottle):
    """Throttle AI generation requests to prevent API cost abuse."""
    scope = 'ai_generation'


class AuthRateThrottle(AnonRateThrottle):
    """Throttle authentication endpoints to prevent brute-force attacks.
    Uses AnonRateThrottle since auth endpoints use AllowAny permission."""
    scope = 'auth'
