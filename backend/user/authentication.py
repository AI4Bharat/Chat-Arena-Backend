from rest_framework import authentication, exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.utils import timezone
from user.models import User
import firebase_admin
from firebase_admin import auth as firebase_auth
import logging

logger = logging.getLogger(__name__)


class FirebaseAuthentication(authentication.BaseAuthentication):
    """
    Firebase authentication using Firebase ID tokens.
    Works with Firebase + custom Django User model.
    """

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION")

        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split("Bearer ")[1]
        try:
            decoded_token = firebase_auth.verify_id_token(token)
            uid = decoded_token.get("uid")

            if not uid:
                raise exceptions.AuthenticationFailed("Invalid Firebase token: missing UID")

            # Fetch or create local user
            user, _ = User.objects.get_or_create(firebase_uid=uid, defaults={"is_active": True})

            # Handle expiration for anonymous users
            if user.is_anonymous and user.anonymous_expires_at:
                if user.anonymous_expires_at < timezone.now():
                    raise exceptions.AuthenticationFailed("Anonymous session expired")

            return (user, None)

        except firebase_auth.InvalidIdTokenError:
            raise exceptions.AuthenticationFailed("Invalid Firebase token")
        except firebase_auth.ExpiredIdTokenError:
            raise exceptions.AuthenticationFailed("Firebase token expired")
        except Exception as e:
            logger.error(f"Firebase authentication error: {str(e)}")
            raise exceptions.AuthenticationFailed("Authentication failed")


class AnonymousTokenAuthentication(authentication.BaseAuthentication):
    """
    Fallback authentication for anonymous users using X-ANONYMOUS-TOKEN header.
    """

    def authenticate(self, request):
        anon_token = request.META.get("HTTP_X_ANONYMOUS_TOKEN")
        if not anon_token:
            return None

        try:
            user = User.objects.get(
                is_anonymous=True,
                preferences__anonymous_token=anon_token,
                is_active=True
            )

            if user.anonymous_expires_at and user.anonymous_expires_at < timezone.now():
                raise exceptions.AuthenticationFailed("Anonymous session expired")

            return (user, None)

        except User.DoesNotExist:
            return None
