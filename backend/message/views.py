from ai_model.llm_interactions import get_model_output
from ai_model.asr_interactions import get_asr_output
from ai_model.tts_interactions import get_tts_output
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
import asyncio
from message.models import Message
from message.serializers import (
    MessageSerializer, MessageCreateSerializer, MessageStreamSerializer,
    MessageTreeSerializer, MessageBranchSerializer, MessageRegenerateSerializer
)
from message.services import MessageService, MessageComparisonService
from message.streaming import StreamingManager
from message.permissions import IsMessageOwner
from chat_session.models import ChatSession
from user.authentication import FirebaseAuthentication, AnonymousTokenAuthentication
from django.db import transaction
from django.http import StreamingHttpResponse
import threading
import queue
from rest_framework.views import APIView
import requests
import os
import base64
import io
import subprocess
import json
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import action
from google.cloud import storage
from django.conf import settings
import datetime
import uuid
import tempfile
from message.utlis import generate_signed_url

class MessageViewSet(viewsets.ModelViewSet):
    """ViewSet for message management"""
    authentication_classes = [FirebaseAuthentication, AnonymousTokenAuthentication]
    permission_classes = [IsAuthenticated, IsMessageOwner]
    queryset = Message.objects.select_related('model', 'session')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return MessageCreateSerializer
        elif self.action == 'stream':
            return MessageStreamSerializer
        elif self.action == 'tree':
            return MessageTreeSerializer
        elif self.action == 'branch':
            return MessageBranchSerializer
        elif self.action == 'regenerate':
            return MessageRegenerateSerializer
        return MessageSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by session
        session_id = self.request.query_params.get('session_id')
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        
        # Filter by role
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('session', 'position')
    
    def create(self, request, *args, **kwargs):
        """Create a new message"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify user owns the session
        session = serializer.validated_data['session']
        if session.user != request.user:
            return Response(
                {'error': 'You do not own this session'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        message = serializer.save()
        
        return Response(
            MessageSerializer(message).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['post'])
    def stream(self, request):
        """Stream a message response"""
        serializer = MessageStreamSerializer(data=request.data.get('messages'), many=True)
        serializer.is_valid(raise_exception=True)
        
        # Get session from last message or session_id
        session_id = request.data.get('session_id')
        if not session_id:
            return Response(
                {'error': 'session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session = get_object_or_404(ChatSession, id=session_id, user=request.user)

        for message in serializer.validated_data:
            if message['role'] == 'user':
                user_message = message
            elif message['role'] == 'assistant':
                if session.mode == 'direct':
                    assistant_message = message
                else:
                    if message['participant'] == 'a':
                        assistant_message_a = message
                    else:
                        assistant_message_b = message
        
        if session.mode == 'random':
            if 'assistant_message_a' in locals() and session.model_a_id:
                assistant_message_a['modelId'] = session.model_a_id
            if 'assistant_message_b' in locals() and session.model_b_id:
                assistant_message_b['modelId'] = session.model_b_id

        # Create user message
        with transaction.atomic():
            user_message = MessageService.create_message(
                session=session,
                message_obj=user_message
            )
            if session.mode == 'direct':
                assistant_message = MessageService.create_message(
                    session=session,
                    message_obj=assistant_message
                )
            else:
                assistant_message_a = MessageService.create_message(
                    session=session,
                    message_obj=assistant_message_a
                )
                assistant_message_b = MessageService.create_message(
                    session=session,
                    message_obj=assistant_message_b
                )
        
        # # Stream response(s)
        # if session.mode == 'compare':
        #     generator = MessageComparisonService.stream_dual_responses(
        #         session=session,
        #         user_message=user_message,
        #         temperature=serializer.validated_data['temperature'],
        #         max_tokens=serializer.validated_data['max_tokens']
        #     )
        # else:
        #     generator = MessageService.stream_assistant_message(
        #         session=session,
        #         user_message=user_message,
        #         assistant_message=assistant_message,
        #     )
            
        # return StreamingManager.create_streaming_response(generator)

        def generate():
            # Capture database alias from session for explicit routing
            db_alias = session._state.db
            
            if session.mode == 'direct':
                try:
                    history = MessageService._get_conversation_history(session)
                    # Remove the last message (current user message) from history to avoid duplication
                    # Only pop if history exists - first message in a new session has empty history
                    if history:
                        history.pop()
                    chunks = []
                    for chunk in get_model_output(
                        system_prompt="We will be rendering your response on a frontend. so please add spaces or indentation or nextline chars or bullet or numberings etc. suitably for code or the text. wherever required, and do not add any comments about this instruction in your response.",
                        user_prompt=user_message.content,
                        history=history,
                        model=session.model_a.model_code,
                    ):
                        if chunk:
                            chunks.append(chunk)
                            escaped_chunk = chunk.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '')
                            yield f'a0:"{escaped_chunk}"\n'
                    
                    assistant_message.content = "".join(chunks)
                    assistant_message.status = 'success'
                    assistant_message.save(using=db_alias)
                    
                    yield 'ad:{"finishReason":"stop"}\n'
                except Exception as e:
                    assistant_message.status = 'error'
                    assistant_message.save(using=db_alias)
                    error_payload = {
                        "finishReason": "error",
                        "error": str(e),
                    }
                    yield f"ad:{json.dumps(error_payload)}\n"
            else:
                chunk_queue = queue.Queue()
        
                def stream_model_a():
                    chunks_a = []
                    try:
                        history = MessageService._get_conversation_history(session, 'a')
                        # Remove the last message from history to avoid duplication
                        # Only pop if history exists - first message in a new session has empty history
                        if history:
                            history.pop()
                        for chunk in get_model_output(
                            system_prompt="We will be rendering your response on a frontend. so please add spaces or indentation or nextline chars or bullet or numberings etc. suitably for code or the text. wherever required, and do not add any comments about this instruction in your response.",
                            user_prompt=user_message.content,
                            history=history,
                            model=session.model_a.model_code,
                        ):
                            if chunk:
                                chunks_a.append(chunk)
                                escaped_chunk = chunk.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '')
                                chunk_queue.put(('a', f'a0:"{escaped_chunk}"\n'))
                        
                        assistant_message_a.content = "".join(chunks_a)
                        assistant_message_a.status = 'success'
                        assistant_message_a.save(using=db_alias)
                        
                        chunk_queue.put(('a', 'ad:{"finishReason":"stop"}\n'))
                        
                    except Exception as e:
                        assistant_message_a.status = 'error'
                        assistant_message_a.save(using=db_alias)
                        error_payload = {
                            "finishReason": "error",
                            "error": str(e),
                        }
                        chunk_queue.put(('a', f"ad:{json.dumps(error_payload)}\n"))
                    finally:
                        chunk_queue.put(('a', None))

                def stream_model_b():
                    chunks_b = []
                    try:
                        history = MessageService._get_conversation_history(session, 'b')
                        # Remove the last message from history to avoid duplication
                        # Only pop if history exists - first message in a new session has empty history
                        if history:
                            history.pop()
                        for chunk in get_model_output(
                            system_prompt="We will be rendering your response on a frontend. so please add spaces or indentation or nextline chars or bullet or numberings etc. suitably for code or the text. wherever required, and do not add any comments about this instruction in your response.",
                            user_prompt=user_message.content,
                            history=history,
                            model=session.model_b.model_code,
                        ):
                            if chunk:
                                chunks_b.append(chunk)
                                escaped_chunk = chunk.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '')
                                chunk_queue.put(('b', f'b0:"{escaped_chunk}"\n'))
                        
                        assistant_message_b.content = "".join(chunks_b)
                        assistant_message_b.status = 'success'
                        assistant_message_b.save(using=db_alias)
                        
                        chunk_queue.put(('b', 'bd:{"finishReason":"stop"}\n'))
                        
                    except Exception as e:
                        assistant_message_b.status = 'error'
                        assistant_message_b.save(using=db_alias)
                        error_payload = {
                            "finishReason": "error",
                            "error": str(e),
                        }
                        chunk_queue.put(('b', f"bd:{json.dumps(error_payload)}\n"))
                    finally:
                        chunk_queue.put(('b', None))

                thread_a = threading.Thread(target=stream_model_a)
                thread_b = threading.Thread(target=stream_model_b)
                
                thread_a.start()
                thread_b.start()
                
                completed = {'a': False, 'b': False}
                
                while not all(completed.values()):
                    try:
                        model, chunk = chunk_queue.get(timeout=0.1)
                        if chunk is None:
                            completed[model] = True
                        else:
                            yield chunk
                    except queue.Empty:
                        continue
                
                thread_a.join()
                thread_b.join()

        def generate_asr_output():
            # Capture database alias from session for explicit routing
            db_alias = session._state.db
            
            if session.mode == 'direct':
                try:
                    # history = MessageService._get_conversation_history(session)
                    # history.pop()

                    output = get_asr_output(generate_signed_url(user_message.audio_path, 120), user_message.language, model=session.model_a.model_code)
                    # escaped_chunk = chunk.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '')
                    yield f'a0:"{output}"\n'
                    
                    assistant_message.content = output
                    assistant_message.status = 'success'
                    assistant_message.save(using=db_alias)
                    
                    yield 'ad:{"finishReason":"stop"}\n'
                except Exception as e:
                    assistant_message.status = 'error'
                    assistant_message.save(using=db_alias)
                    error_payload = {
                        "finishReason": "error",
                        "error": str(e),
                    }
                    yield f"ad:{json.dumps(error_payload)}\n"
            else:
                chunk_queue = queue.Queue()
        
                def stream_model_a():
                    try:
                        # history = MessageService._get_conversation_history(session, 'a')
                        # history.pop()
                        output_a = get_asr_output(generate_signed_url(user_message.audio_path, 120), user_message.language, model=session.model_a.model_code)
                        chunk_queue.put(('a', f'a0:"{output_a}"\n'))
                        
                        assistant_message_a.content = output_a
                        assistant_message_a.status = 'success'
                        assistant_message_a.save(using=db_alias)
                        
                        chunk_queue.put(('a', 'ad:{"finishReason":"stop"}\n'))
                        
                    except Exception as e:
                        assistant_message_a.status = 'error'
                        assistant_message_a.save(using=db_alias)
                        error_payload = {
                            "finishReason": "error",
                            "error": str(e),
                        }
                        chunk_queue.put(('a', f"ad:{json.dumps(error_payload)}\n"))
                    finally:
                        chunk_queue.put(('a', None))

                def stream_model_b():
                    try:
                        # history = MessageService._get_conversation_history(session, 'b')
                        # history.pop()
                        output_b = get_asr_output(generate_signed_url(user_message.audio_path, 120), user_message.language, model=session.model_b.model_code)
                        chunk_queue.put(('b', f'b0:"{output_b}"\n'))
                        
                        assistant_message_b.content = output_b
                        assistant_message_b.status = 'success'
                        assistant_message_b.save(using=db_alias)
                        
                        chunk_queue.put(('b', 'bd:{"finishReason":"stop"}\n'))
                        
                    except Exception as e:
                        assistant_message_b.status = 'error'
                        assistant_message_b.save(using=db_alias)
                        error_payload = {
                            "finishReason": "error",
                            "error": str(e),
                        }
                        chunk_queue.put(('b', f"bd:{json.dumps(error_payload)}\n"))
                    finally:
                        chunk_queue.put(('b', None))

                thread_a = threading.Thread(target=stream_model_a)
                thread_b = threading.Thread(target=stream_model_b)
                
                thread_a.start()
                thread_b.start()
                
                completed = {'a': False, 'b': False}
                
                while not all(completed.values()):
                    try:
                        model, chunk = chunk_queue.get(timeout=0.1)
                        if chunk is None:
                            completed[model] = True
                        else:
                            yield chunk
                    except queue.Empty:
                        continue
                
                thread_a.join()
                thread_b.join()

        def generate_tts_output():
            if session.mode == 'direct':
                try:
                    # history = MessageService._get_conversation_history(session)
                    # history.pop()

                    output = get_tts_output(user_message.content, user_message.language, model=session.model_a.model_code)
                    # escaped_chunk = chunk.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '')
                    yield f'a0:"{output["url"]}"\n'
                    
                    assistant_message.audio_path = output["path"]
                    assistant_message.status = 'success'
                    assistant_message.save()
                    
                    yield 'ad:{"finishReason":"stop"}\n'
                except Exception as e:
                    assistant_message.status = 'error'
                    assistant_message.save()
                    error_payload = {
                        "finishReason": "error",
                        "error": str(e),
                    }
                    yield f"ad:{json.dumps(error_payload)}\n"
            else:
                chunk_queue = queue.Queue()
        
                def stream_model_a():
                    try:
                        # history = MessageService._get_conversation_history(session, 'a')
                        # history.pop()
                        output_a = get_tts_output(user_message.content, user_message.language, model=session.model_a.model_code)
                        chunk_queue.put(('a', f'a0:"{output_a["url"]}"\n'))
                        
                        assistant_message_a.audio_path = output_a["path"]
                        assistant_message_a.status = 'success'
                        assistant_message_a.save()
                        
                        chunk_queue.put(('a', 'ad:{"finishReason":"stop"}\n'))
                        
                    except Exception as e:
                        assistant_message_a.status = 'error'
                        assistant_message_a.save()
                        error_payload = {
                            "finishReason": "error",
                            "error": str(e),
                        }
                        chunk_queue.put(('a', f"ad:{json.dumps(error_payload)}\n"))
                    finally:
                        chunk_queue.put(('a', None))

                def stream_model_b():
                    try:
                        # history = MessageService._get_conversation_history(session, 'b')
                        # history.pop()
                        output_b = get_tts_output(user_message.content, user_message.language, model=session.model_b.model_code)
                        chunk_queue.put(('b', f'b0:"{output_b["url"]}"\n'))
                        
                        assistant_message_b.audio_path = output_b["path"]
                        assistant_message_b.status = 'success'
                        assistant_message_b.save()
                        
                        chunk_queue.put(('b', 'bd:{"finishReason":"stop"}\n'))
                        
                    except Exception as e:
                        assistant_message_b.status = 'error'
                        assistant_message_b.save()
                        error_payload = {
                            "finishReason": "error",
                            "error": str(e),
                        }
                        chunk_queue.put(('b', f"bd:{json.dumps(error_payload)}\n"))
                    finally:
                        chunk_queue.put(('b', None))

                thread_a = threading.Thread(target=stream_model_a)
                thread_b = threading.Thread(target=stream_model_b)
                
                thread_a.start()
                thread_b.start()
                
                completed = {'a': False, 'b': False}
                
                while not all(completed.values()):
                    try:
                        model, chunk = chunk_queue.get(timeout=0.1)
                        if chunk is None:
                            completed[model] = True
                        else:
                            yield chunk
                    except queue.Empty:
                        continue
                
                thread_a.join()
                thread_b.join()
    
        if session.session_type == 'ASR':
            return StreamingHttpResponse(generate_asr_output(), content_type='text/plain')
        elif session.session_type == 'TTS':
            return StreamingHttpResponse(generate_tts_output(), content_type='text/plain')
        else:
            return StreamingHttpResponse(generate(), content_type='text/plain')

    @action(detail=True, methods=['post'])
    def regenerate(self, request, pk=None):
        """Regenerate a specific assistant message"""
        try:
            assistant_message = self.get_object()
            
            if assistant_message.role != 'assistant':
                return Response(
                    {'error': 'Can only regenerate assistant messages'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            parent_message_id = assistant_message.parent_message_ids[0] if assistant_message.parent_message_ids else None
            if not parent_message_id:
                return Response(
                    {'error': 'No parent message found'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user_message = Message.objects.get(id=parent_message_id, session=assistant_message.session)
            
            # assistant_message.content = ""
            assistant_message.status = "pending"
            assistant_message.save()
            
            session = assistant_message.session
            
            def generate():
                # Capture database alias from session for explicit routing
                db_alias = session._state.db
                
                participant = assistant_message.participant
                history = MessageService._get_conversation_history(session, participant)
                if participant == None:
                    participant = 'a'
                
                try:                
                    if history and history[-1]['role'] == 'assistant':
                        history.pop()
                    if history and history[-1]['role'] == 'user':
                        history.pop()
                    
                    chunks = []
                    model = session.model_a if participant == 'a' else session.model_b
                    for chunk in get_model_output(
                        system_prompt="We will be rendering your response on a frontend. so please add spaces or indentation or nextline chars or bullet or numberings etc. suitably for code or the text. wherever required, and do not add any comments about this instruction in your response.",
                        user_prompt=user_message.content,
                        history=history,
                        model=model.model_code,
                    ):
                        if chunk:
                            chunks.append(chunk)
                            escaped_chunk = chunk.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '')
                            yield f'{participant}0:"{escaped_chunk}"\n'
                    
                    assistant_message.content = "".join(chunks)
                    assistant_message.status = 'success'
                    assistant_message.save(using=db_alias)
                    yield f'{participant}d:{{"finishReason":"stop"}}\n'
                except Exception as e:
                    assistant_message.status = 'error'
                    assistant_message.save(using=db_alias)
                    error_payload = {
                        "finishReason": "error",
                        "error": str(e),
                    }
                    yield f"{participant}d:{json.dumps(error_payload)}\n"

            def generate_asr_output():
                # Capture database alias from session for explicit routing
                db_alias = session._state.db
                
                participant = assistant_message.participant
                if participant == None:
                    participant = 'a'
                try:
                    model = session.model_a if participant == 'a' else session.model_b
                    output = get_asr_output(generate_signed_url(user_message.audio_path, 120), user_message.language, model=model.model_code)
                    yield f'{participant}0:"{output}"\n'
                    
                    assistant_message.content = output
                    assistant_message.status = 'success'
                    assistant_message.save(using=db_alias)
                    yield f'{participant}d:{{"finishReason":"stop"}}\n'
                except Exception as e:
                    assistant_message.status = 'error'
                    assistant_message.save(using=db_alias)
                    error_payload = {
                        "finishReason": "error",
                        "error": str(e),
                    }
                    yield f"{participant}d:{json.dumps(error_payload)}\n"

            def generate_tts_output():
                participant = assistant_message.participant
                if participant == None:
                    participant = 'a'
                try:
                    model = session.model_a if participant == 'a' else session.model_b
                    output = get_tts_output(user_message.content, user_message.language, model=model.model_code)
                    yield f'{participant}0:"{output["url"]}"\n'
                    
                    assistant_message.audio_path = output["path"]
                    assistant_message.status = 'success'
                    assistant_message.save()
                    yield f'{participant}d:{{"finishReason":"stop"}}\n'
                except Exception as e:
                    assistant_message.status = 'error'
                    assistant_message.save()
                    error_payload = {
                        "finishReason": "error",
                        "error": str(e),
                    }
                    yield f"{participant}d:{json.dumps(error_payload)}\n"

            if session.session_type == 'ASR':
                return StreamingHttpResponse(generate_asr_output(), content_type='text/plain')
            elif session.session_type == 'TTS':
                return StreamingHttpResponse(generate_tts_output(), content_type='text/plain')
            else:
                return StreamingHttpResponse(generate(), content_type='text/plain')
            
        except Message.DoesNotExist:
            return Response(
                {'error': 'Message not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        
    @action(detail=True, methods=['get'])
    def tree(self, request, pk=None):
        """Get message tree starting from this message"""
        message = self.get_object()
        
        # Find root messages
        root_messages = []
        current = message
        
        while current.parent_message_ids:
            parent_id = current.parent_message_ids[0]  # Follow first parent
            try:
                current = Message.objects.get(id=parent_id)
            except Message.DoesNotExist:
                break
        
        root_messages.append(current)
        
        # Build tree from root
        tree = MessageService.get_message_tree(current.id)
        
        return Response(tree)
    
    @action(detail=True, methods=['post'])
    def branch(self, request, pk=None):
        """Create a branch from this message"""
        parent_message = self.get_object()
        serializer = MessageBranchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        branch_message = MessageService.create_branch(
            parent_message=parent_message,
            content=serializer.validated_data['content'],
            branch_type=serializer.validated_data.get('branch_type', 'alternative')
        )
        
        return Response(
            MessageSerializer(branch_message).data,
            status=status.HTTP_201_CREATED
        )
    
    # @action(detail=True, methods=['post'])
    # def regenerate(self, request, pk=None):
    #     """Regenerate an assistant message"""
    #     message = self.get_object()
    #     serializer = MessageRegenerateSerializer(data=request.data)
    #     serializer.is_valid(raise_exception=True)
        
    #     # Create regenerated message
    #     new_message = MessageService.regenerate_message(
    #         message=message,
    #         **serializer.validated_data
    #     )
        
    #     # Stream the regenerated response
    #     generator = MessageService.stream_assistant_message(
    #         session=message.session,
    #         user_message=Message.objects.get(id=message.parent_message_ids[0]),
    #         model=new_message.model,
    #         participant=message.participant,
    #         temperature=serializer.validated_data['temperature'],
    #         max_tokens=serializer.validated_data['max_tokens']
    #     )
        
    #     # Update the new message ID in the generator
    #     async def update_generator():
    #         async for item in generator:
    #             if item.get('message_id'):
    #                 item['message_id'] = str(new_message.id)
    #             yield item
        
    #     return StreamingManager.create_streaming_response(update_generator())
    
    @action(detail=False, methods=['get'])
    def conversation_path(self, request):
        """Get conversation path between two messages"""
        start_id = request.query_params.get('start_id')
        end_id = request.query_params.get('end_id')
        
        if not start_id or not end_id:
            return Response(
                {'error': 'start_id and end_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start_message = Message.objects.get(id=start_id)
            end_message = Message.objects.get(id=end_id)
        except Message.DoesNotExist:
            return Response(
                {'error': 'Message not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Find path between messages
        path = MessageService.find_conversation_path(start_message, end_message)
        
        return Response({
            'path': MessageSerializer(path, many=True).data,
            'distance': len(path)
        })

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_audio(self, request):
        if 'audio' not in request.FILES:
            return Response({'error': 'No audio provided'}, status=status.HTTP_400_BAD_REQUEST)

        audio_file = request.FILES['audio']

        try:
            # Save original file temporarily
            temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio_file.name)[1])
            for chunk in audio_file.chunks():
                temp_input.write(chunk)
            temp_input.close()

            # Output WAV temp file
            temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_output_path = temp_output.name
            temp_output.close()

            # Convert using ffmpeg (subprocess method)
            ffmpeg_cmd = [
                "ffmpeg",
                "-y",  # Overwrite
                "-i", temp_input.name,  # input file
                "-ac", "1",             # mono
                "-ar", "16000",         # 16k sample rate (best for ASR)
                "-f", "wav",
                temp_output_path
            ]

            result = subprocess.run(
                ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            if result.returncode != 0:
                return Response({
                    "error": "FFmpeg conversion failed",
                    "details": result.stderr.decode()
                }, status=500)

            # Upload the WAV file to GCS
            client = storage.Client()
            bucket = client.bucket(settings.GS_BUCKET_NAME)

            blob_name = f"asr-audios/{uuid.uuid4()}.wav"
            blob = bucket.blob(blob_name)

            with open(temp_output_path, "rb") as f:
                blob.upload_from_file(f, content_type="audio/wav")

            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(minutes=15),
                method="GET",
            )

            # Cleanup temporary files
            os.remove(temp_input.name)
            os.remove(temp_output_path)

            return Response({
                "path": blob_name,
                "url": signed_url,
            }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

#   def upload_audio(self, request):
#         if 'audio' not in request.FILES:
#             return Response({'error': 'No audio provided'}, status=status.HTTP_400_BAD_REQUEST)
            
#         audio_file = request.FILES['audio']
#         try:
#             client = storage.Client()
#             bucket = client.bucket(settings.GS_BUCKET_NAME)
#             ext = os.path.splitext(audio_file.name)[1]
#             blob_name = f"asr-audios/{uuid.uuid4()}{ext}"
#             blob = bucket.blob(blob_name)
#             blob.upload_from_file(audio_file, content_type=audio_file.content_type)
            
#             signed_url = blob.generate_signed_url(
#                 version="v4",
#                 expiration=datetime.timedelta(minutes=15),
#                 method="GET",
#             )
            
#             return Response({
#                 'path': blob_name,
#                 'url': signed_url,
#             }, status=status.HTTP_200_OK)
            
#         except Exception as e:
#             return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TransliterationAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, target_language, data, *args, **kwargs):
        response_transliteration = requests.get(
            os.getenv("TRANSLITERATION_URL") + target_language + "/" + data,
            headers={"Authorization": "Bearer " + os.getenv("TRANSLITERATION_KEY")},
        )

        transliteration_output = response_transliteration.json()
        return Response(transliteration_output, status=status.HTTP_200_OK)

def convert_audio_base64_to_mp3(input_base64):
    input_audio_bytes = base64.b64decode(input_base64)
    input_buffer = io.BytesIO(input_audio_bytes)

    ffmpeg_command = [
        'ffmpeg', '-i', 'pipe:0',
        '-f', 'mp3',
        'pipe:1'
    ]

    try:
        process = subprocess.Popen(
            ffmpeg_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        output_mp3_bytes, error = process.communicate(input=input_buffer.read())

        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {error.decode()}")

        output_base64_mp3 = base64.b64encode(output_mp3_bytes).decode('utf-8')
        return output_base64_mp3

    except Exception as e:
        print(f"Audio conversion error: {e}")
        return None
        
class TranscribeAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        data = request.data
        audio_base64 = data.get("audioBase64")
        lang = data.get("lang", "hi")
        mp3_base64 = convert_audio_base64_to_mp3(audio_base64)

        chunk_data = {
            "config": {
                "serviceId": os.getenv("DHRUVA_SERVICE_ID") if lang != "en" else os.getenv("DHRUVA_SERVICE_ID_EN"),
                "language": {"sourceLanguage": lang},
                "transcriptionFormat": {"value": "transcript"}
                },
            "audio": [
                {
                    "audioContent":mp3_base64
                    }
                ]
            }
        try:
            response = requests.post(os.getenv("DHRUVA_API_URL"),
            headers={"authorization": os.getenv("DHRUVA_KEY")},
            json=chunk_data,
            )
            transcript = response.json()["output"][0]["source"]
            return Response({"transcript": transcript+" " or ""}, status=status.HTTP_200_OK)
        except Exception as e:
            print("Error:", e)
            return Response({"message": "Failed to transcribe"}, status=status.HTTP_400_BAD_REQUEST)