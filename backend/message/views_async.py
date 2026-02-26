"""
Async Message Views
Async ViewSet for message streaming operations (ASGI only)
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from asgiref.sync import sync_to_async
import json
import uuid
from typing import AsyncGenerator

from message.models import Message
from message.serializers import MessageSerializer, MessageStreamSerializer
from message.services_async import MessageServiceAsync
from chat_session.models import ChatSession
from ai_model.models import AIModel


class MessageViewSetAsync(viewsets.ViewSet):
    """
    Async ViewSet for message operations
    Use this in ASGI mode for streaming endpoints
    """
    permission_classes = [IsAuthenticated]

    # ========================================================================
    # DATABASE HELPERS (sync_to_async wrappers)
    # ========================================================================

    @sync_to_async
    def get_session(self, session_id: str, user):
        """Get session for user"""
        return get_object_or_404(
            ChatSession.objects.select_related('model_a', 'model_b'),
            id=session_id,
            user=user
        )

    @sync_to_async
    def get_model(self, model_id: str):
        """Get AI model"""
        return get_object_or_404(AIModel, id=model_id)

    # ========================================================================
    # STREAMING ENDPOINT
    # ========================================================================

    @action(detail=False, methods=['post'])
    async def stream(self, request):
        """
        Stream message response asynchronously
        
        POST /api/messages/stream/
        Body:
        {
            "session_id": "uuid",
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        """
        # Validate request
        serializer = MessageStreamSerializer(
            data=request.data.get('messages'),
            many=True
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get session
        session_id = request.data.get('session_id')
        if not session_id:
            return Response(
                {'error': 'session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        session = await self.get_session(session_id, request.user)

        # Parse messages
        messages = serializer.validated_data
        user_message_data = next(
            (m for m in messages if m['role'] == 'user'),
            None
        )

        if not user_message_data:
            return Response(
                {'error': 'No user message provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Route based on session mode
        if session.mode == 'direct':
            return StreamingHttpResponse(
                self._stream_direct_mode(session, user_message_data, request),
                content_type='text/event-stream'
            )
        elif session.mode == 'compare':
            return StreamingHttpResponse(
                self._stream_compare_mode(session, user_message_data, request),
                content_type='text/event-stream'
            )
        else:
            return Response(
                {'error': f'Unsupported mode: {session.mode}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    async def _stream_direct_mode(
        self,
        session: ChatSession,
        user_message_data: dict,
        request
    ) -> AsyncGenerator[str, None]:
        """Stream response for direct mode (single model)"""
        
        # Create user message
        user_message_obj = {
            'id': str(uuid.uuid4()),
            'role': 'user',
            'content': user_message_data['content'],
            'parent_message_ids': [],
            'participant': None,
            'modelId': None,
            'image_path': user_message_data.get('image_path'),
            'audio_path': user_message_data.get('audio_path'),
            'doc_path': user_message_data.get('doc_path'),
            'language': user_message_data.get('language'),
        }

        user_message = await MessageServiceAsync.create_message_sync(
            session=session,
            message_obj=user_message_obj
        )

        # Create assistant message placeholder
        assistant_message_obj = {
            'id': str(uuid.uuid4()),
            'role': 'assistant',
            'content': '',
            'parent_message_ids': [str(user_message.id)],
            'participant': None,
            'modelId': str(session.model_a.id) if session.model_a else None
        }

        assistant_message = await MessageServiceAsync.create_message_sync(
            session=session,
            message_obj=assistant_message_obj
        )

        # Stream response
        try:
            async for chunk_data in MessageServiceAsync.stream_assistant_message_async(
                session=session,
                user_message=user_message,
                assistant_message=assistant_message,
                model=session.model_a
            ):
                # Format as Server-Sent Events
                if chunk_data['type'] == 'stream':
                    # Send chunk
                    yield f"a0:{json.dumps({'content': chunk_data['chunk']})}\n"
                
                elif chunk_data['type'] == 'complete':
                    # Send completion
                    yield f"ad:{json.dumps({'finishReason': 'stop'})}\n"
                
                elif chunk_data['type'] == 'error':
                    # Send error
                    yield f"ad:{json.dumps({'error': chunk_data['error']})}\n"

        except Exception as e:
            yield f"ad:{json.dumps({'error': str(e)})}\n"

    async def _stream_compare_mode(
        self,
        session: ChatSession,
        user_message_data: dict,
        request
    ) -> AsyncGenerator[str, None]:
        """Stream responses for compare mode (two models)"""
        
        # Create user message
        user_message_obj = {
            'id': str(uuid.uuid4()),
            'role': 'user',
            'content': user_message_data['content'],
            'parent_message_ids': [],
            'participant': None,
            'modelId': None,
            'image_path': user_message_data.get('image_path'),
            'audio_path': user_message_data.get('audio_path'),
            'doc_path': user_message_data.get('doc_path'),
            'language': user_message_data.get('language'),
        }

        user_message = await MessageServiceAsync.create_message_sync(
            session=session,
            message_obj=user_message_obj
        )

        # Create assistant message placeholders for both models
        assistant_message_a_obj = {
            'id': str(uuid.uuid4()),
            'role': 'assistant',
            'content': '',
            'parent_message_ids': [str(user_message.id)],
            'participant': 'a',
            'modelId': str(session.model_a.id) if session.model_a else None
        }

        assistant_message_a = await MessageServiceAsync.create_message_sync(
            session=session,
            message_obj=assistant_message_a_obj
        )

        assistant_message_b_obj = {
            'id': str(uuid.uuid4()),
            'role': 'assistant',
            'content': '',
            'parent_message_ids': [str(user_message.id)],
            'participant': 'b',
            'modelId': str(session.model_b.id) if session.model_b else None
        }

        assistant_message_b = await MessageServiceAsync.create_message_sync(
            session=session,
            message_obj=assistant_message_b_obj
        )

        # Stream both responses concurrently
        try:
            async for chunk_data in MessageServiceAsync.stream_dual_responses_async(
                session=session,
                user_message=user_message,
                assistant_message_a=assistant_message_a,
                assistant_message_b=assistant_message_b
            ):
                participant = chunk_data.get('participant', 'a')
                
                if chunk_data['type'] == 'stream':
                    # Send chunk with participant prefix
                    yield f"{participant}0:{json.dumps({'content': chunk_data['chunk']})}\n"
                
                elif chunk_data['type'] == 'complete':
                    # Send completion
                    yield f"{participant}d:{json.dumps({'finishReason': 'stop'})}\n"
                
                elif chunk_data['type'] == 'error':
                    # Send error
                    yield f"{participant}d:{json.dumps({'error': chunk_data['error']})}\n"

        except Exception as e:
            yield f"ad:{json.dumps({'error': str(e)})}\n"

    # ========================================================================
    # REGENERATE ENDPOINT
    # ========================================================================

    @action(detail=True, methods=['post'])
    async def regenerate(self, request, pk=None):
        """
        Regenerate an assistant message
        
        POST /api/messages/{id}/regenerate/
        """
        # Get original message
        message = await sync_to_async(
            lambda: get_object_or_404(Message, id=pk, session__user=request.user)
        )()

        if message.role != 'assistant':
            return Response(
                {'error': 'Can only regenerate assistant messages'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Stream regenerated response
        async def generate():
            try:
                async for chunk_data in MessageServiceAsync.regenerate_message_async(
                    original_message=message
                ):
                    participant = chunk_data.get('participant', 'a')
                    
                    if chunk_data['type'] == 'stream':
                        yield f"{participant}0:{json.dumps({'content': chunk_data['chunk']})}\n"
                    
                    elif chunk_data['type'] == 'complete':
                        yield f"{participant}d:{json.dumps({'finishReason': 'stop'})}\n"
                    
                    elif chunk_data['type'] == 'error':
                        yield f"{participant}d:{json.dumps({'error': chunk_data['error']})}\n"

            except Exception as e:
                yield f"ad:{json.dumps({'error': str(e)})}\n"

        return StreamingHttpResponse(
            generate(),
            content_type='text/event-stream'
        )

    # ========================================================================
    # REGULAR CRUD ENDPOINTS (Keep sync for now)
    # ========================================================================

    def list(self, request):
        """List messages (sync - not frequently used)"""
        from asgiref.sync import async_to_sync
        # Use sync version for now
        from message.views import MessageViewSet
        sync_viewset = MessageViewSet()
        sync_viewset.request = request
        return sync_viewset.list(request)

    def retrieve(self, request, pk=None):
        """Get single message (sync)"""
        from message.views import MessageViewSet
        sync_viewset = MessageViewSet()
        sync_viewset.request = request
        return sync_viewset.retrieve(request, pk)

    def create(self, request):
        """Create message (sync)"""
        from message.views import MessageViewSet
        sync_viewset = MessageViewSet()
        sync_viewset.request = request
        return sync_viewset.create(request)


# ============================================================================
# SIMPLE FUNCTION-BASED ASYNC VIEW (Alternative)
# ============================================================================

from rest_framework.decorators import api_view, permission_classes

@api_view(['POST'])
@permission_classes([IsAuthenticated])
async def stream_message_simple(request):
    """
    Simplified async streaming endpoint
    
    POST /api/messages/stream-simple/
    Body:
    {
        "session_id": "uuid",
        "message": "Hello"
    }
    """
    session_id = request.data.get('session_id')
    message_content = request.data.get('message')

    if not session_id or not message_content:
        return Response(
            {'error': 'session_id and message required'},
            status=400
        )

    # Get session
    @sync_to_async
    def get_session():
        return get_object_or_404(
            ChatSession.objects.select_related('model_a'),
            id=session_id,
            user=request.user
        )

    session = await get_session()

    # Stream response
    async def generate():
        try:
            from message.services_async import create_and_stream_message
            
            async for chunk_data in create_and_stream_message(
                session_id=session_id,
                user_message_content=message_content
            ):
                if chunk_data['type'] == 'stream':
                    yield f"data: {json.dumps({'content': chunk_data['chunk']})}\n\n"
                elif chunk_data['type'] == 'complete':
                    yield f"data: {json.dumps({'done': True})}\n\n"
                elif chunk_data['type'] == 'error':
                    yield f"data: {json.dumps({'error': chunk_data['error']})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingHttpResponse(
        generate(),
        content_type='text/event-stream'
    )
