from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404
from django.db.models import Count, Prefetch, Q
from message.models import Message
from chat_session.models import ChatSession
from feedback.models import Feedback

# Maximum number of detailed votes allowed in TTS Academic mode
MAX_ACADEMIC_TTS_VOTES = 60
from chat_session.serializers import (
    ChatSessionSerializer, ChatSessionCreateSerializer,
    ChatSessionListSerializer, ChatSessionShareSerializer,
    ChatSessionDuplicateSerializer, ChatSessionExportSerializer,
    ChatSessionRetrieveSerializer
)
from chat_session.services import ChatSessionService
from chat_session.permissions import IsSessionOwner, CanAccessSharedSession
from user.authentication import FirebaseAuthentication, AnonymousTokenAuthentication
from ai_model.llm_interactions import get_model_output
import re
from message.utlis import generate_signed_url


class ChatSessionViewSet(viewsets.ModelViewSet):
    """ViewSet for chat session management"""
    authentication_classes = [FirebaseAuthentication, AnonymousTokenAuthentication]
    permission_classes = [IsAuthenticated, IsSessionOwner]
    
    def get_queryset(self):
        user = self.request.user
        queryset = ChatSession.objects.select_related('model_a', 'model_b', 'user')
        
        # Filter based on action
        if self.action == 'shared':
            # For shared endpoint, return public sessions
            queryset = queryset.filter(is_public=True)
        else:
            # For other actions, return user's sessions
            queryset = queryset.filter(user=user)
        
        # Add message count annotation for list view
        if self.action == 'list':
            queryset = queryset.annotate(
                _message_count=Count('messages')
            )
        
        # Apply filters
        mode = self.request.query_params.get('mode')
        if mode:
            queryset = queryset.filter(mode=mode)
        
        # Search in title
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(title__icontains=search)
        
        # Date filters
        created_after = self.request.query_params.get('created_after')
        if created_after:
            queryset = queryset.filter(created_at__gte=created_after)
        
        created_before = self.request.query_params.get('created_before')
        if created_before:
            queryset = queryset.filter(created_at__lte=created_before)
        
        # Model filter
        model_id = self.request.query_params.get('model_id')
        if model_id:
            queryset = queryset.filter(
                Q(model_a_id=model_id) | Q(model_b_id=model_id)
            )
        
        return queryset.order_by('-updated_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ChatSessionCreateSerializer
        elif self.action == 'list':
            return ChatSessionListSerializer
        elif self.action in ['share', 'unshare']:
            return ChatSessionShareSerializer
        elif self.action == 'duplicate':
            return ChatSessionDuplicateSerializer
        elif self.action == 'export':
            return ChatSessionExportSerializer
        elif self.action == 'filtered_by_type':
            return ChatSessionListSerializer
        return ChatSessionSerializer
    
    def _get_academic_tts_votes_count(self, user):
        """Get count of detailed votes submitted in TTS Academic mode"""
        return Feedback.objects.filter(
            user=user,
            session__mode='academic',
            session__session_type='TTS',
            additional_feedback_json__isnull=False
        ).exclude(
            additional_feedback_json={}
        ).count()

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            mode = serializer.validated_data['mode']
            session_type = serializer.validated_data.get('session_type')

            if mode == 'academic' and session_type == 'TTS':
                if not request.user.is_anonymous:
                    votes_count = self._get_academic_tts_votes_count(request.user)
                    if votes_count >= MAX_ACADEMIC_TTS_VOTES:
                        return Response(
                            {
                                'error': 'academic_vote_limit_reached',
                                'message': 'Thanks for your contributions! You have submitted the maximum limit of votes in this Academic Benchmark.',
                                'votes_count': votes_count,
                                'max_votes': MAX_ACADEMIC_TTS_VOTES
                            },
                            status=status.HTTP_403_FORBIDDEN
                        )

            # Handle random and academic modes (both use random model selection)
            if serializer.validated_data['mode'] in ['random', 'academic']:
                session = ChatSessionService.create_session_with_random_models(
                    user=request.user,
                    mode=serializer.validated_data['mode'],
                    metadata=serializer.validated_data.get('metadata'),
                    session_type=serializer.validated_data.get('session_type'),
                )
            else:
                session = serializer.save()
            
            # Return full serializer data
            return Response(
                ChatSessionSerializer(session, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            from common.error_logging import log_and_respond, create_log_context
            log_context = create_log_context(request)
            return log_and_respond(
                e,
                endpoint='/sessions/',
                log_context=log_context
            )
    
    @action(detail=False, methods=['get'], url_path='type')
    def filtered_by_type(self, request):
        """
        Returns sessions filtered by session_type
        """
        session_type = request.query_params.get('session_type')
        qs = self.get_queryset()

        if session_type:
            qs = qs.filter(session_type=session_type)

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        """Share a session publicly"""
        session = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        serializer.update(session, serializer.validated_data)
        
        return Response({
            'share_token': session.share_token,
            'share_url': ChatSessionSerializer(
                session, 
                context={'request': request}
            ).data['share_url']
        })
    
    @action(detail=True, methods=['post'])
    def unshare(self, request, pk=None):
        """Unshare a session"""
        session = self.get_object()
        session.is_public = False
        session.share_token = None
        session.save()
        
        return Response({'status': 'unshared'})
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Duplicate a session"""
        session = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        new_session = ChatSessionService.duplicate_session(
            session=session,
            user=request.user,
            include_messages=serializer.validated_data.get('include_messages', False),
            new_title=serializer.validated_data.get('new_title')
        )
        
        return Response(
            ChatSessionSerializer(new_session, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['get'])
    def export(self, request, pk=None):
        """Export session data"""
        session = self.get_object()
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        content, content_type = ChatSessionService.export_session(
            session=session,
            **serializer.validated_data
        )
        
        # Determine filename
        format = serializer.validated_data['format']
        filename = f"chat_session_{session.id}.{format}"
        
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get session statistics"""
        session = self.get_object()
        stats = ChatSessionService.get_session_statistics(session)
        
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def shared(self, request):
        """Get public shared sessions"""
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def trending(self, request):
        """Get trending sessions"""
        limit = int(request.query_params.get('limit', 10))
        trending_sessions = ChatSessionService.get_trending_sessions(limit=limit)
        
        serializer = ChatSessionSerializer(
            trending_sessions, 
            many=True,
            context={'request': request}
        )
        
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def transfer_ownership(self, request, pk=None):
        """Transfer session ownership to authenticated user"""
        session = self.get_object()
        
        # Only allow transfer from anonymous to authenticated users
        if not session.user.is_anonymous:
            return Response(
                {'error': 'Can only transfer sessions from anonymous users'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if request.user.is_anonymous:
            return Response(
                {'error': 'Cannot transfer to anonymous user'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Transfer ownership
        old_user = session.user
        session.user = request.user
        session.expires_at = None  # Remove expiration
        session.metadata['transferred_from'] = str(old_user.id)
        session.metadata['transferred_at'] = timezone.now().isoformat()
        session.save()
        
        return Response({
            'status': 'transferred',
            'session_id': str(session.id)
        })
    
    def retrieve(self, request, *args, **kwargs):
        """Get session details with messages"""
        try:
            session = self.get_object()
            
            messages = Message.objects.filter(
                session=session
            ).order_by('-position')[:50]
            
            session_data = ChatSessionRetrieveSerializer(session, context={'request': request}).data
            
            response_data = {
                'session': session_data,
                'messages': [
                    {
                        'id': str(msg.id),
                        'role': msg.role,
                        'content': msg.content,
                        'position': msg.position,
                        'participant': msg.participant,
                        'status': msg.status,
                        'feedback': msg.feedback,
                        'created_at': msg.created_at.isoformat(),
                        'audio_path': msg.audio_path,
                        'language': msg.language,
                        'has_detailed_feedback': msg.has_detailed_feedback,
                        **({'temp_audio_url': generate_signed_url(msg.audio_path)} if msg.audio_path else {})
                    }
                    for msg in reversed(messages)
                ]
            }
            
            return Response(response_data)
        except Exception as e:
            from common.error_logging import log_and_respond, create_log_context
            log_context = create_log_context(request, session_id=kwargs.get('pk'))
            return log_and_respond(
                e,
                endpoint='/sessions/{id}/',
                log_context=log_context
            )
    
    @action(detail=True, methods=['post'])
    def generate_title(self, request, pk=None):
        """Generate AI-based title for the session"""
        session = self.get_object()
        
        if session.session_type == "LLM" or session.session_type == "TTS":
            message = session.messages.filter(role='user').first()
        else:
            message = session.messages.filter(role='assistant').first()
        if not message:
            return Response({'error': 'No messages in session'}, status=400)
        
        prompt_llm = f"""Based on this message, create a brief title (max 5 words).

        Message: {message.content}

        Rules:
        - No quotes or quotation marks
        - No colons or special punctuation
        - Simple, direct phrasing
        - Capitalize appropriately
        - Be descriptive but concise

        Return only the title text, nothing else."""

        prompt_tts = f"""Based on this text that will be spoken by an AI voice, create a brief title (max 5 words).

        Message: {message.content}

        Rules:
        - No quotes or quotation marks
        - No colons or special punctuation
        - Simple, direct phrasing
        - Capitalize appropriately
        - Be descriptive but concise
        - Describe the content being narrated

        Return only the title text, nothing else."""
        
        try:
            title_chunks = []
            for chunk in get_model_output(
                system_prompt="You are a helpful assistant that creates short, descriptive titles.",
                user_prompt=prompt_tts if session.session_type == "TTS" else prompt_llm,
                history=[],
                model="GPT3.5"
            ):
                if chunk:
                    title_chunks.append(chunk)
            
            generated_title = ''.join(title_chunks).strip()
            generated_title = re.sub(r'^"(.*)"$', r'\1', generated_title)
            
            if len(generated_title) > 50:
                generated_title = generated_title[:47] + "..."
            
            session.title = generated_title
            session.save(update_fields=['title'])
            
            return Response({'title': generated_title})
            
        except Exception as e:
            # Log the error with detailed context
            from common.error_logging import log_endpoint_error_to_gcs, extract_endpoint_error_details, create_log_context
            log_context = create_log_context(request, session_id=session.id)
            error_details = extract_endpoint_error_details(e, '/sessions/generate_title/', log_context)
            log_endpoint_error_to_gcs(error_details)
            
            # Fallback to using message content as title (existing logic preserved)
            fallback_title = message.content[:50]
            if len(message.content) > 50:
                fallback_title += "..."
            
            session.title = fallback_title
            session.save(update_fields=['title'])
            
            return Response({'title': fallback_title})

class SharedChatSessionView(viewsets.ReadOnlyModelViewSet):
    """View for accessing shared sessions via share token"""
    authentication_classes = []  # No authentication required
    permission_classes = [CanAccessSharedSession]
    serializer_class = ChatSessionSerializer
    lookup_field = 'share_token'
    
    def get_queryset(self):
        return ChatSession.objects.filter(
            share_token__isnull=False
        ).select_related('model_a', 'model_b', 'user')
    
    def get_object(self):
        share_token = self.kwargs.get('share_token')
        
        # Try to get by share token - must be public
        try:
            session = ChatSession.objects.get(share_token=share_token, is_public=True)
            return session
        except ChatSession.DoesNotExist:
            raise Http404("Session not found")

    def retrieve(self, request, *args, **kwargs):
        """Get session details with messages"""
        session = self.get_object()
        
        # Fetch messages for this session
        messages = Message.objects.filter(
            session=session
        ).order_by('position')
        
        response_data = {
            'session': ChatSessionSerializer(
                session, 
                context={'request': request}
            ).data,
            'messages': [
                {
                    'id': str(msg.id),
                    'role': msg.role,
                    'content': msg.content,
                    'position': msg.position,
                    'participant': msg.participant,
                    'status': msg.status,
                    'feedback': msg.feedback,
                    'created_at': msg.created_at.isoformat(),
                    'audio_path': msg.audio_path,
                    'language': msg.language,
                    'temp_audio_url': generate_signed_url(msg.audio_path)
                }
                for msg in messages
            ]
        }
        
        return Response(response_data)
