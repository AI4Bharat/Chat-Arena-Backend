from django.conf import settings
from django.core.cache import cache
from typing import Optional, Dict
import jwt
import requests
from datetime import datetime, timedelta
from django.utils import timezone
import logging
from .models import User
from chat_session.models import ChatSession
from feedback.models import Feedback

logger = logging.getLogger(__name__)


class TokenGenerator:
    """Generate and validate custom tokens for anonymous users"""
    
    @staticmethod
    def generate_anonymous_token(user_id: str) -> str:
        """Generate a JWT token for anonymous users"""
        payload = {
            'user_id': user_id,
            'type': 'anonymous',
            'exp': datetime.utcnow() + timedelta(days=30),
            'iat': datetime.utcnow()
        }
        
        token = jwt.encode(
            payload,
            settings.SECRET_KEY,
            algorithm='HS256'
        )
        
        return token
    
    @staticmethod
    def validate_anonymous_token(token: str) -> Optional[Dict]:
        """Validate anonymous token and return payload"""
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=['HS256']
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Anonymous token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid anonymous token: {e}")
            return None


class UserActivityTracker:
    """Track user activity for analytics"""
    
    @staticmethod
    def track_login(user, login_type='google'):
        """Track user login event"""
        cache_key = f"user_login_{user.id}_{datetime.now().date()}"
        cache.set(cache_key, True, timeout=86400)  # 24 hours
        
        # Update last login in preferences
        if not user.preferences:
            user.preferences = {}
        
        user.preferences['last_login'] = datetime.now().isoformat()
        user.preferences['login_count'] = user.preferences.get('login_count', 0) + 1
        user.save(update_fields=['preferences', 'updated_at'])
    
    @staticmethod
    def track_activity(user, activity_type, metadata=None):
        """Track general user activity"""
        activity_data = {
            'user_id': str(user.id),
            'type': activity_type,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        
        # Store in cache for batch processing
        cache_key = f"user_activity_{user.id}"
        activities = cache.get(cache_key, [])
        activities.append(activity_data)
        cache.set(cache_key, activities, timeout=3600)  # 1 hour
    
    @staticmethod
    def get_user_activity_summary(user):
        """Get summary of user activities"""
        cache_key = f"user_activity_{user.id}"
        activities = cache.get(cache_key, [])
        
        summary = {
            'total_activities': len(activities),
            'activity_types': {},
            'last_activity': None
        }
        
        for activity in activities:
            activity_type = activity['type']
            summary['activity_types'][activity_type] = \
                summary['activity_types'].get(activity_type, 0) + 1
        
        if activities:
            summary['last_activity'] = max(
                activities, 
                key=lambda x: x['timestamp']
            )['timestamp']
        
        return summary


class GoogleAuthHelper:
    """Helper functions for Google authentication"""
    
    @staticmethod
    def get_google_user_info(access_token: str) -> Optional[Dict]:
        """Get user info from Google using access token"""
        try:
            response = requests.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {access_token}'}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get Google user info: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting Google user info: {e}")
            return None
    
    @staticmethod
    def verify_google_id_token(id_token: str) -> Optional[Dict]:
        """Verify Google ID token without Firebase"""
        try:
            # This is a fallback if Firebase is not available
            response = requests.get(
                f'https://oauth2.googleapis.com/tokeninfo?id_token={id_token}'
            )
            
            if response.status_code == 200:
                token_info = response.json()
                # Verify the audience (client ID)
                if token_info.get('aud') == settings.GOOGLE_CLIENT_ID:
                    return token_info
                    
            return None
            
        except Exception as e:
            logger.error(f"Error verifying Google ID token: {e}")
            return None


def cleanup_expired_anonymous_users():
    """Cleanup expired anonymous users - to be run as a periodic task"""
    
    expired_users = User.objects.filter(
        is_anonymous=True,
        anonymous_expires_at__lt=timezone.now()
    )
    
    count = 0
    for user in expired_users:
        # Optional: Archive their data before deletion
        sessions_count = user.chat_sessions.count()
        if sessions_count > 0:
            # Log or archive if needed
            logger.info(f"Deleting anonymous user {user.id} with {sessions_count} sessions")
        
        user.delete()
        count += 1
    
    logger.info(f"Cleaned up {count} expired anonymous users")
    return count


def merge_user_data(source_user, target_user):
    """Merge data from source user to target user"""
    
    # Update all related objects
    ChatSession.objects.filter(user=source_user).update(user=target_user)
    Feedback.objects.filter(user=source_user).update(user=target_user)
    
    # Merge preferences
    if source_user.preferences:
        target_user.preferences = {
            **target_user.preferences,
            **source_user.preferences,
            'merged_from': str(source_user.id),
            'merged_at': datetime.now().isoformat()
        }
        target_user.save()
    
    # Delete source user
    source_user.delete()
    
    logger.info(f"Merged user {source_user.id} into {target_user.id}")