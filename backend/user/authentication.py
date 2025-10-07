from rest_framework import authentication, exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.utils import timezone
from user.models import User
import logging

logger = logging.getLogger(__name__)


class FirebaseUserWrapper:
    """Wraps a User object to provide Django-like properties for DRF"""
    def __init__(self, user: User):
        self.user = user

    @property
    def is_authenticated(self):
        return True  # Always True for Firebase authenticated users

    @property
    def is_anonymous(self):
        return self.user.is_anonymous

    def __getattr__(self, name):
        return getattr(self.user, name)


class AnonymousUserWrapper:
    """Wraps anonymous users to provide Django-like properties"""
    def __init__(self, user: User):
        self.user = user

    @property
    def is_authenticated(self):
        return True  # Considered authenticated for DRF permission checks

    @property
    def is_anonymous(self):
        return True

    def __getattr__(self, name):
        return getattr(self.user, name)


class FirebaseAuthentication(JWTAuthentication):
    """JWT authentication using Firebase tokens"""
    def get_user(self, validated_token):
        try:
            user_id = validated_token.get('user_id')
            user = User.objects.get(id=user_id, is_active=True)

            # Expire anonymous users
            if user.is_anonymous and user.anonymous_expires_at:
                if user.anonymous_expires_at < timezone.now():
                    raise exceptions.AuthenticationFailed('Anonymous session expired')

            return FirebaseUserWrapper(user)

        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('User not found')


class AnonymousTokenAuthentication(authentication.BaseAuthentication):
    """Authentication for anonymous sessions using X-Anonymous-Token header"""
    def authenticate(self, request):
        anon_token = request.META.get('HTTP_X_ANONYMOUS_TOKEN')
        if not anon_token:
            return None

        try:
            user = User.objects.get(
                is_anonymous=True,
                preferences__anonymous_token=anon_token,
                is_active=True
            )

            # Check expiration
            if user.anonymous_expires_at and user.anonymous_expires_at < timezone.now():
                raise exceptions.AuthenticationFailed('Anonymous session expired')

            return (AnonymousUserWrapper(user), None)

        except User.DoesNotExist:
            return None
