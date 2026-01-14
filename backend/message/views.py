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
import random
from academic_prompts.models import AcademicPrompt
from django.db.models import Min

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
        
        if session.mode == 'random' or session.mode == 'academic':
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
                    # Generate signed URL for image if present
                    image_url = None
                    if hasattr(user_message, 'image_path') and user_message.image_path:
                        image_url = generate_signed_url(user_message.image_path, 900)
                    
                    # Document logic
                    prompt_content = user_message.content
                    if hasattr(user_message, 'doc_path') and user_message.doc_path:
                        try:
                            # Ensure metadata dict exists
                            if not user_message.metadata:
                                user_message.metadata = {}
                            
                            # Extract if not already cached
                            if 'extracted_text' not in user_message.metadata:
                                from message.document_utils import extract_text_from_document
                                doc_text = extract_text_from_document(user_message.doc_path)
                                if doc_text:
                                    user_message.metadata['extracted_text'] = doc_text
                                    user_message.save(update_fields=['metadata'])
                            
                            # Use cached text
                            doc_text = user_message.metadata.get('extracted_text')
                            if doc_text:
                                prompt_content += f"\n\n[Attached Document Content]:\n{doc_text}"
                        except Exception as e:
                            print(f"Error processing document: {e}")
                    
                    # Audio transcription logic for direct mode
                    if hasattr(user_message, 'audio_path') and user_message.audio_path:
                        try:
                            # Ensure metadata dict exists
                            if not user_message.metadata:
                                user_message.metadata = {}
                            
                            # Transcribe if not already cached
                            if 'audio_transcription' not in user_message.metadata:
                                language = getattr(user_message, 'language', None) or 'en'
                                audio_url = generate_signed_url(user_message.audio_path, 120)
                                transcription = get_asr_output(audio_url, language)
                                user_message.metadata['audio_transcription'] = transcription
                                user_message.save(update_fields=['metadata'])
                            
                            # Use cached transcription
                            audio_transcription = user_message.metadata.get('audio_transcription')
                            if audio_transcription:
                                prompt_content += f"\n\n[Audio Transcription]:\n{audio_transcription}"
                        except Exception as e:
                            print(f"Error processing audio: {e}")
                    
                    for chunk in get_model_output(
                        system_prompt="We will be rendering your response on a frontend. so please add spaces or indentation or nextline chars or bullet or numberings etc. suitably for code or the text. wherever required, and do not add any comments about this instruction in your response.",
                        user_prompt=prompt_content,
                        history=history,
                        model=session.model_a.model_code,
                        image_url=image_url,
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
                        # Generate signed URL for image if present
                        image_url = None
                        if hasattr(user_message, 'image_path') and user_message.image_path:
                            image_url = generate_signed_url(user_message.image_path, 900)
                        
                        # Document logic
                        prompt_content = user_message.content
                        if hasattr(user_message, 'doc_path') and user_message.doc_path:
                            try:
                                # Ensure metadata dict exists
                                if not user_message.metadata:
                                    user_message.metadata = {}
                                
                                # Extract if not already cached
                                if 'extracted_text' not in user_message.metadata:
                                    from message.document_utils import extract_text_from_document
                                    doc_text = extract_text_from_document(user_message.doc_path)
                                    if doc_text:
                                        user_message.metadata['extracted_text'] = doc_text
                                        user_message.save(update_fields=['metadata'])
                                
                                # Use cached text
                                doc_text = user_message.metadata.get('extracted_text')
                                if doc_text:
                                    prompt_content += f"\n\n[Attached Document Content]:\n{doc_text}"
                            except Exception as e:
                                print(f"Error processing document: {e}")
                        
                        # Audio transcription logic
                        if hasattr(user_message, 'audio_path') and user_message.audio_path:
                            try:
                                # Ensure metadata dict exists
                                if not user_message.metadata:
                                    user_message.metadata = {}
                                
                                # Transcribe if not already cached
                                if 'audio_transcription' not in user_message.metadata:
                                    language = getattr(user_message, 'language', None) or 'en'
                                    audio_url = generate_signed_url(user_message.audio_path, 120)
                                    transcription = get_asr_output(audio_url, language)
                                    user_message.metadata['audio_transcription'] = transcription
                                    user_message.save(update_fields=['metadata'])
                                
                                # Use cached transcription
                                audio_transcription = user_message.metadata.get('audio_transcription')
                                if audio_transcription:
                                    prompt_content += f"\n\n[Audio Transcription]:\n{audio_transcription}"
                            except Exception as e:
                                print(f"Error processing audio: {e}")
                        
                        for chunk in get_model_output(
                            system_prompt="We will be rendering your response on a frontend. so please add spaces or indentation or nextline chars or bullet or numberings etc. suitably for code or the text. wherever required, and do not add any comments about this instruction in your response.",
                            user_prompt=prompt_content,
                            history=history,
                            model=session.model_a.model_code,
                            image_url=image_url,
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
                        # Generate signed URL for image if present
                        image_url = None
                        if hasattr(user_message, 'image_path') and user_message.image_path:
                            image_url = generate_signed_url(user_message.image_path, 900)
                        
                        # Document logic
                        prompt_content = user_message.content
                        if hasattr(user_message, 'doc_path') and user_message.doc_path:
                            try:
                                # Ensure metadata dict exists
                                if not user_message.metadata:
                                    user_message.metadata = {}
                                
                                # Extract if not already cached
                                if 'extracted_text' not in user_message.metadata:
                                    from message.document_utils import extract_text_from_document
                                    doc_text = extract_text_from_document(user_message.doc_path)
                                    if doc_text:
                                        user_message.metadata['extracted_text'] = doc_text
                                        user_message.save(update_fields=['metadata'])
                                
                                # Use cached text
                                doc_text = user_message.metadata.get('extracted_text')
                                if doc_text:
                                    prompt_content += f"\n\n[Attached Document Content]:\n{doc_text}"
                            except Exception as e:
                                print(f"Error processing document: {e}")
                        
                        # Audio transcription logic
                        if hasattr(user_message, 'audio_path') and user_message.audio_path:
                            try:
                                # Ensure metadata dict exists
                                if not user_message.metadata:
                                    user_message.metadata = {}
                                
                                # Transcribe if not already cached
                                if 'audio_transcription' not in user_message.metadata:
                                    language = getattr(user_message, 'language', None) or 'en'
                                    audio_url = generate_signed_url(user_message.audio_path, 120)
                                    transcription = get_asr_output(audio_url, language)
                                    user_message.metadata['audio_transcription'] = transcription
                                    user_message.save(update_fields=['metadata'])
                                
                                # Use cached transcription
                                audio_transcription = user_message.metadata.get('audio_transcription')
                                if audio_transcription:
                                    prompt_content += f"\n\n[Audio Transcription]:\n{audio_transcription}"
                            except Exception as e:
                                print(f"Error processing audio: {e}")
                                audio_transcription = user_message.metadata.get('audio_transcription')
                                if audio_transcription:
                                    prompt_content += f"\n\n[Audio Transcription]:\n{audio_transcription}"
                        
                        for chunk in get_model_output(
                            system_prompt="We will be rendering your response on a frontend. so please add spaces or indentation or nextline chars or bullet or numberings etc. suitably for code or the text. wherever required, and do not add any comments about this instruction in your response.",
                            user_prompt=prompt_content,
                            history=history,
                            model=session.model_b.model_code,
                            image_url=image_url,
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
            # For academic mode, get random prompt from database
            if session.mode == 'academic':
                language = user_message.language

                # Get least used prompt for uniform distribution
                prompts = AcademicPrompt.objects.filter(language=language, is_active=True)
                if prompts.exists():
                    min_usage_count = prompts.aggregate(Min('usage_count'))['usage_count__min']
                    least_used_prompts = prompts.filter(usage_count=min_usage_count)
                    selected_prompt = random.choice(list(least_used_prompts))

                    # Update user message with the selected prompt
                    user_message.content = selected_prompt.text
                    user_message.save(update_fields=['content'])

                    selected_prompt.increment_usage()
                    escaped_prompt = selected_prompt.text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                    yield f'prompt:"{escaped_prompt}"\n'

            gender = random.choice(["male", "female"])
            if session.mode == 'direct':
                try:
                    # history = MessageService._get_conversation_history(session)
                    # history.pop()

                    output = get_tts_output(user_message.content, user_message.language, model=session.model_a.model_code, gender=gender)
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
                        output_a = get_tts_output(user_message.content, user_message.language, model=session.model_a.model_code, gender=gender)
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
                        output_b = get_tts_output(user_message.content, user_message.language, model=session.model_b.model_code, gender=gender)
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
                    # Generate signed URL for image if present
                    image_url = None
                    if hasattr(user_message, 'image_path') and user_message.image_path:
                        image_url = generate_signed_url(user_message.image_path, 900)
                    
                    # Document logic
                    prompt_content = user_message.content
                    if hasattr(user_message, 'doc_path') and user_message.doc_path:
                        try:
                            # Ensure metadata dict exists
                            if not user_message.metadata:
                                user_message.metadata = {}
                            
                            # Extract if not already cached
                            if 'extracted_text' not in user_message.metadata:
                                from message.document_utils import extract_text_from_document
                                doc_text = extract_text_from_document(user_message.doc_path)
                                if doc_text:
                                    user_message.metadata['extracted_text'] = doc_text
                                    user_message.save(update_fields=['metadata'])
                            
                            # Use cached text
                            doc_text = user_message.metadata.get('extracted_text')
                            if doc_text:
                                prompt_content += f"\n\n[Attached Document Content]:\n{doc_text}"
                        except Exception as e:
                            print(f"Error processing document: {e}")
                    
                    # Audio transcription logic
                    if hasattr(user_message, 'audio_path') and user_message.audio_path:
                        try:
                            # Ensure metadata dict exists
                            if not user_message.metadata:
                                user_message.metadata = {}
                            
                            # Transcribe if not already cached
                            if 'audio_transcription' not in user_message.metadata:
                                language = getattr(user_message, 'language', None) or 'en'
                                audio_url = generate_signed_url(user_message.audio_path, 120)
                                transcription = get_asr_output(audio_url, language)
                                user_message.metadata['audio_transcription'] = transcription
                                user_message.save(update_fields=['metadata'])
                            
                            # Use cached transcription
                            audio_transcription = user_message.metadata.get('audio_transcription')
                            if audio_transcription:
                                prompt_content += f"\n\n[Audio Transcription]:\n{audio_transcription}"
                        except Exception as e:
                            print(f"Error processing audio: {e}")
                    
                    for chunk in get_model_output(
                        system_prompt="We will be rendering your response on a frontend. so please add spaces or indentation or nextline chars or bullet or numberings etc. suitably for code or the text. wherever required, and do not add any comments about this instruction in your response.",
                        user_prompt=prompt_content,
                        history=history,
                        model=model.model_code,
                        image_url=image_url,
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
    def upload_image(self, request):
        if 'image' not in request.FILES:
            return Response({'error': 'No image provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        image_file = request.FILES['image']
        try:
            client = storage.Client()
            bucket = client.bucket(settings.GS_BUCKET_NAME)
            ext = os.path.splitext(image_file.name)[1]
            blob_name = f"llm-images-input/{uuid.uuid4()}{ext}"
            blob = bucket.blob(blob_name)
            blob.upload_from_file(image_file, content_type=image_file.content_type)
            
            signed_url = generate_signed_url(blob_name)
            
            return Response({
                'path': blob_name,
                'url': signed_url,
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_audio(self, request):
        if 'audio' not in request.FILES:
            return Response({'error': 'No audio provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        audio_file = request.FILES['audio']
        
        # Validate file type - allow common audio formats
        allowed_types = [
            'audio/mpeg',  # mp3
            'audio/mp3',
            'audio/wav',
            'audio/wave',
            'audio/x-wav',
            'audio/ogg',
            'audio/webm',
            'audio/mp4',
            'audio/m4a',
            'audio/x-m4a',
        ]
        
        if audio_file.content_type not in allowed_types:
            return Response({
                'error': f'Invalid audio file type: {audio_file.content_type}. Allowed types: mp3, wav, ogg, webm, m4a'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate file size (max 50MB for audio)
        if audio_file.size > 50 * 1024 * 1024:
            return Response({
                'error': 'Audio file size must be less than 50MB'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Save original file temporarily
            temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio_file.name)[1])
            for chunk in audio_file.chunks():
                temp_input.write(chunk)
            temp_input.close()
            
            # Check audio duration using ffprobe
            ffprobe_cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1:noprint_wrappers=1",
                temp_input.name
            ]
            
            try:
                duration_result = subprocess.run(
                    ffprobe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10
                )
                
                if duration_result.returncode == 0:
                    duration = float(duration_result.stdout.strip())
                    # Check if duration exceeds 1 minute (60 seconds)
                    if duration > 60:
                        os.remove(temp_input.name)
                        return Response({
                            'error': f'Audio duration must be less than 1 minute. Your audio is {duration:.1f} seconds.'
                        }, status=status.HTTP_400_BAD_REQUEST)
            except (ValueError, subprocess.TimeoutExpired):
                # If we can't get duration, proceed with conversion (fallback)
                pass

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
                # Cleanup on failure
                os.remove(temp_input.name)
                if os.path.exists(temp_output_path):
                    os.remove(temp_output_path)
                    
                return Response({
                    "error": "FFmpeg conversion failed",
                    "details": result.stderr.decode()
                }, status=500)

            # Upload the WAV file to GCS
            client = storage.Client()
            bucket = client.bucket(settings.GS_BUCKET_NAME)

            # Use asr-audios folder as it seems preferred for ASR
            blob_name = f"asr-audios/{uuid.uuid4()}.wav"
            blob = bucket.blob(blob_name)

            with open(temp_output_path, "rb") as f:
                blob.upload_from_file(f, content_type="audio/wav")

            # Cleanup temporary files
            os.remove(temp_input.name)
            os.remove(temp_output_path)
            
            signed_url = generate_signed_url(blob_name)
            
            return Response({
                'path': blob_name,
                'url': signed_url,
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            # Attempt cleanup if temp files exist
            try:
                if 'temp_input' in locals(): os.remove(temp_input.name)
                if 'temp_output_path' in locals(): os.remove(temp_output_path)
            except:
                pass
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_document(self, request):
        if 'document' not in request.FILES:
            return Response({'error': 'No document provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        doc_file = request.FILES['document']
        
        # Validate file type - allow common document formats
        allowed_types = [
            'application/pdf',  # PDF
            'application/msword',  # DOC
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # DOCX
            'text/plain',  # TXT
            'text/markdown',  # MD
            'application/rtf',  # RTF
            'application/vnd.ms-excel',  # XLS
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # XLSX
            'text/csv',  # CSV
        ]
        
        if doc_file.content_type not in allowed_types:
            return Response({
                'error': f'Invalid document type: {doc_file.content_type}. Allowed: PDF, DOC, DOCX, TXT, MD, RTF, XLS, XLSX, CSV'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate file size (max 20MB for documents)
        if doc_file.size > 20 * 1024 * 1024:
            return Response({
                'error': 'Document size must be less than 20MB'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            client = storage.Client()
            bucket = client.bucket(settings.GS_BUCKET_NAME)
            ext = os.path.splitext(doc_file.name)[1]
            blob_name = f"llm-documents-input/{uuid.uuid4()}{ext}"
            blob = bucket.blob(blob_name)
            blob.upload_from_file(doc_file, content_type=doc_file.content_type)
            
            signed_url = generate_signed_url(blob_name)
            
            return Response({
                'path': blob_name,
                'url': signed_url,
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
