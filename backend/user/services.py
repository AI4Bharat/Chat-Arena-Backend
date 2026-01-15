from django.conf import settings
from django.utils import timezone
from typing import Optional, Dict
import logging
import uuid
import os
from rest_framework_simplejwt.tokens import RefreshToken
from user.models import User
from chat_session.models import ChatSession
import firebase_admin
from firebase_admin import credentials, auth

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    try:
        # Path to service account key
        cred_path = os.path.join(settings.BASE_DIR, 'arena_backend/serviceAccountKey.json')

        # Log the path for debugging
        logger.info(f"Loading Firebase credentials from: {cred_path}")

        # Check if file exists
        if not os.path.exists(cred_path):
            logger.error(f"Firebase credentials file not found at: {cred_path}")
            raise FileNotFoundError(f"Firebase credentials not found at: {cred_path}")

        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        raise


class UserService:
    @staticmethod
    def get_tokens_for_user(user: User) -> Dict[str, str]:
        """Generate JWT tokens for a user"""
        refresh = RefreshToken.for_user(user)
        
        # Add custom claims
        refresh['user_id'] = str(user.id)
        refresh['email'] = user.email
        refresh['is_anonymous'] = user.is_anonymous
        refresh['auth_provider'] = user.auth_provider
        
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'token_type': 'Bearer',
            'expires_in': settings.SIMPLE_JWT.get('ACCESS_TOKEN_LIFETIME').total_seconds()
        }
    
    @staticmethod
    def verify_google_token_with_pyrebase(id_token: str) -> Optional[Dict]:
        """Verify Google ID token using Firebase Admin SDK"""
        try:
            # Verify the token with Firebase Admin SDK
            decoded_token = auth.verify_id_token(id_token)

            # Get user info from Firebase
            firebase_user = auth.get_user(decoded_token['uid'])

            # Return user info in a format compatible with our code
            return {
                'localId': firebase_user.uid,
                'email': firebase_user.email,
                'displayName': firebase_user.display_name,
                'phoneNumber': firebase_user.phone_number,
            }
        except Exception as e:
            logger.error(f"Error verifying Google token with Firebase Admin SDK: {e}")
            return None
    
    @staticmethod
    def get_or_create_google_user(google_user_info: dict) -> User:
        """Get or create user from Google auth info"""
        email = google_user_info.get('email')
        uid = google_user_info.get('localId')  # Pyrebase uses localId
        display_name = google_user_info.get('displayName', email.split('@')[0] if email else 'User')
        
        try:
            user = User.objects.get(firebase_uid=uid)
            # Update user info if changed
            if user.email != email:
                user.email = email
            if user.display_name != display_name:
                user.display_name = display_name
            user.save()
        except User.DoesNotExist:
            user = User.objects.create(
                firebase_uid=uid,
                email=email,
                display_name=display_name,
                auth_provider='google',
                is_anonymous=False
            )

        return user

    @staticmethod
    def verify_phone_token_with_pyrebase(id_token: str) -> Optional[Dict]:
        """Verify Phone ID token using Firebase Admin SDK"""
        try:
            logger.info("Starting phone token verification with Firebase Admin SDK")

            # Verify the token with Firebase Admin SDK
            decoded_token = auth.verify_id_token(id_token)
            logger.info(f"Token decoded successfully for UID: {decoded_token.get('uid')}")

            # Get user info from Firebase
            firebase_user = auth.get_user(decoded_token['uid'])
            logger.info(f"Firebase user retrieved: {firebase_user.uid}, phone: {firebase_user.phone_number}")

            # Return user info in a format compatible with our code
            return {
                'localId': firebase_user.uid,
                'email': firebase_user.email,
                'displayName': firebase_user.display_name,
                'phoneNumber': firebase_user.phone_number,
            }
        except Exception as e:
            logger.error(f"Error verifying Phone token with Firebase Admin SDK: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    @staticmethod
    def get_or_create_phone_user(phone_user_info: dict, display_name: str) -> User:
        """Get or create user from Phone auth info"""
        phone_number = phone_user_info.get('phoneNumber')
        uid = phone_user_info.get('localId')  # Pyrebase uses localId

        if not phone_number:
            raise ValueError("Phone number not found in user info")

        if not display_name:
            raise ValueError("Display name is required for phone authentication")

        try:
            user = User.objects.get(firebase_uid=uid)
            # Update user info if changed
            if user.phone_number != phone_number:
                user.phone_number = phone_number
            if user.display_name != display_name:
                user.display_name = display_name
            user.save()
        except User.DoesNotExist:
            user = User.objects.create(
                firebase_uid=uid,
                phone_number=phone_number,
                display_name=display_name,
                auth_provider='phone',
                is_anonymous=False
            )

        return user
    
    @staticmethod
    def create_anonymous_user(display_name: Optional[str] = None) -> User:
        """Create an anonymous user"""
        
        if not display_name:
            display_name = f"Anonymous_{str(uuid.uuid4())[:8]}"
            
        user = User.objects.create(
            display_name=display_name,
            auth_provider='anonymous',
            is_anonymous=True
        )
        
        # Generate anonymous token
        anon_token = str(uuid.uuid4())
        user.preferences['anonymous_token'] = anon_token
        user.save()
        
        return user
    
    @staticmethod
    def update_user_preferences(user: User, preferences: Dict) -> User:
        """Update user preferences"""
        if not user.preferences:
            user.preferences = {}
        
        user.preferences.update(preferences)
        user.save()
        return user
    
    @staticmethod
    def merge_anonymous_to_authenticated(
        anonymous_user: User, 
        authenticated_user: User
    ) -> User:
        """Merge anonymous user data to authenticated user"""
        # Transfer chat sessions
        ChatSession.objects.filter(user=anonymous_user).update(
            user=authenticated_user
        )
        
        # Merge preferences
        if anonymous_user.preferences:
            authenticated_user.preferences = {
                **authenticated_user.preferences,
                **anonymous_user.preferences
            }
            authenticated_user.save()
        
        # Delete anonymous user
        anonymous_user.delete()
        
        return authenticated_user