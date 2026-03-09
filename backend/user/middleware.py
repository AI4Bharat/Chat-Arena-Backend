from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from user.models import User
from user.services import UserService


class WebSocketAuthMiddleware:
    """
    Custom middleware to authenticate WebSocket connections using tokens
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Try to authenticate user from query string token
        query_string = scope.get('query_string', b'').decode()
        
        if 'token=' in query_string:
            token = query_string.split('token=')[-1].split('&')[0]
            scope['user'] = await self.get_user_from_token(token)
        else:
            scope['user'] = AnonymousUser()
        
        return await self.app(scope, receive, send)
    
    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            # First try SimpleJWT token
            try:
                from rest_framework_simplejwt.authentication import JWTAuthentication
                from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
                
                jwt_auth = JWTAuthentication()
                validated_token = jwt_auth.get_validated_token(token)
                
                # The payload has 'user_id' which matches our User.id 
                user_id = validated_token.get('user_id')
                if user_id:
                    user = User.objects.get(id=user_id)
                    if getattr(user, 'is_active', True):
                        return user
            except Exception as e:
                import traceback
                print(f"SimpleJWT error: {e}")
                traceback.print_exc()

            # Then try Firebase token
            firebase_user = UserService.verify_firebase_token(token)
            
            if firebase_user:
                return User.objects.get(firebase_uid=firebase_user['uid'])
            
            # Then try anonymous token
            user = User.objects.filter(
                is_anonymous=True,
                preferences__anonymous_token=token
            ).first()
            
            return user or AnonymousUser()
            
        except Exception:
            return AnonymousUser()