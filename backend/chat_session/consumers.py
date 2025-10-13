import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from urllib.parse import parse_qs
from chat_session.models import ChatSession
from message.models import Message

logger = logging.getLogger(__name__)


class ChatSessionConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time chat session updates"""
    
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.session_group_name = f'session_{self.session_id}'
        self.user = None
        
        # Authenticate user first
        if not await self.authenticate_user():
            logger.warning(f"WebSocket connection rejected - authentication failed for session {self.session_id}")
            await self.close()
            return
        
        # Verify user has access to this session
        if not await self.verify_session_access():
            logger.warning(f"WebSocket connection rejected - no access to session {self.session_id}")
            await self.close()
            return
        
        # Join session group
        await self.channel_layer.group_add(
            self.session_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Log successful connection
        logger.info(f"WebSocket connected: user={self.user.id}, session={self.session_id}")
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'user': {
                'id': str(self.user.id),
                'display_name': self.user.display_name,
                'is_anonymous': self.user.is_anonymous
            }
        }))
        
        # Send initial session state
        await self.send_session_state()
    
    async def disconnect(self, close_code):
        # Leave session group
        await self.channel_layer.group_discard(
            self.session_group_name,
            self.channel_name
        )
        logger.info(f"WebSocket disconnected: user={self.user.id if self.user else 'unknown'}, code={close_code}")
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }))
            
            elif message_type == 'typing_indicator':
                # Broadcast typing indicator to other users
                await self.channel_layer.group_send(
                    self.session_group_name,
                    {
                        'type': 'typing_indicator',
                        'user_id': str(self.user.id),
                        'is_typing': data.get('is_typing', False)
                    }
                )
            
            elif message_type == 'request_state':
                await self.send_session_state()
                
        except Exception as e:
            logger.error(f"Error in receive: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))
    
    async def typing_indicator(self, event):
        # Don't send typing indicator back to sender
        if event['user_id'] != str(self.user.id):
            await self.send(text_data=json.dumps({
                'type': 'typing_indicator',
                'user_id': event['user_id'],
                'is_typing': event['is_typing']
            }))
    
    async def message_update(self, event):
        """Handle message updates"""
        await self.send(text_data=json.dumps({
            'type': 'message_update',
            'message': event['message'],
            'action': event.get('action', 'created')
        }))
    
    async def session_update(self, event):
        """Handle session updates"""
        await self.send(text_data=json.dumps({
            'type': 'session_update',
            'session': event['session'],
            'action': event.get('action', 'updated')
        }))
    
    async def authenticate_user(self):
        """Authenticate user via JWT or anonymous token"""
        # Get token from query string or headers
        query_string = self.scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        
        # Try to get JWT token
        token = query_params.get('token', [None])[0]
        
        if not token:
            # Try to get from headers (for newer WebSocket implementations)
            headers = dict(self.scope.get('headers', []))
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        # Authenticate with JWT
        if token:
            self.user = await self.authenticate_jwt(token)
            if self.user:
                self.scope['user'] = self.user  # Set user in scope for compatibility
                return True
        
        # Try anonymous token as fallback
        anon_token = query_params.get('anonymous_token', [None])[0]
        if anon_token:
            self.user = await self.authenticate_anonymous(anon_token)
            if self.user:
                self.scope['user'] = self.user  # Set user in scope for compatibility
                return True
        
        return False
    
    @database_sync_to_async
    def authenticate_jwt(self, token):
        """Authenticate user with JWT token"""
        try:
            # Validate token
            validated_token = AccessToken(token)
            user_id = validated_token.get('user_id')
            
            # Get user
            from user.models import User
            user = User.objects.get(id=user_id, is_active=True)
            
            # Check if anonymous user is expired
            if user.is_anonymous and user.anonymous_expires_at:
                from django.utils import timezone
                if user.anonymous_expires_at < timezone.now():
                    return None
            
            return user
            
        except (InvalidToken, TokenError) as e:
            logger.error(f"JWT authentication failed: {e}")
            return None
        except User.DoesNotExist:
            logger.error(f"User not found for JWT token")
            return None
    
    @database_sync_to_async
    def authenticate_anonymous(self, anon_token):
        """Authenticate anonymous user with token"""
        try:
            from user.models import User
            from django.utils import timezone
            
            user = User.objects.get(
                is_anonymous=True,
                preferences__anonymous_token=anon_token,
                is_active=True
            )
            
            # Check if expired
            if user.anonymous_expires_at and user.anonymous_expires_at < timezone.now():
                return None
            
            return user
            
        except User.DoesNotExist:
            logger.error(f"Anonymous user not found for token")
            return None
    
    @database_sync_to_async
    def verify_session_access(self):
        """Verify user has access to this session"""
        try:
            session = ChatSession.objects.get(id=self.session_id)
            user = self.user  # Use authenticated user
            
            # Check if user owns the session or it's public
            if session.user == user or session.is_public:
                return True
            
            # Check for share token in query params
            query_string = self.scope.get('query_string', b'').decode()
            query_params = parse_qs(query_string)
            share_token = query_params.get('share_token', [None])[0]
            
            if share_token and session.share_token == share_token:
                return True
            
            return False
        except ChatSession.DoesNotExist:
            return False
    
    @database_sync_to_async
    def get_session_state(self):
        """Get current session state"""
        session = ChatSession.objects.select_related(
            'model_a', 'model_b', 'user'
        ).get(id=self.session_id)
        
        # Get recent messages
        messages = Message.objects.filter(
            session=session
        ).order_by('-position')[:50]
        
        return {
            'session': {
                'id': str(session.id),
                'mode': session.mode,
                'title': session.title,
                'model_a': {
                    'id': str(session.model_a.id),
                    'display_name': session.model_a.display_name
                } if session.model_a else None,
                'model_b': {
                    'id': str(session.model_b.id),
                    'display_name': session.model_b.display_name
                } if session.model_b else None,
            },
            'messages': [
                {
                    'id': str(msg.id),
                    'role': msg.role,
                    'content': msg.content,
                    'position': msg.position,
                    'participant': msg.participant,
                    'status': msg.status,
                    'feedback': msg.feedback,
                    'created_at': msg.created_at.isoformat()
                }
                for msg in reversed(messages)
            ]
        }
    
    async def send_session_state(self):
        """Send current session state to client"""
        state = await self.get_session_state()
        await self.send(text_data=json.dumps({
            'type': 'session_state',
            **state
        }))