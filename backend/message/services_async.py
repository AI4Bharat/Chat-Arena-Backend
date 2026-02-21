"""
Async Message Service
Async versions of message service methods for use with ASGI
"""

from django.utils import timezone
from typing import List, Dict, Optional, AsyncGenerator
from asgiref.sync import sync_to_async
import json

from message.models import Message, MessageRelation
from chat_session.models import ChatSession
from ai_model.models import AIModel
from message.serializers import MessageSerializer
from channels.layers import get_channel_layer
from ai_model.llm_interactions_async import get_model_output_async


class MessageServiceAsync:
    """Async service for managing messages"""

    # ========================================================================
    # DATABASE WRAPPERS (sync_to_async)
    # ========================================================================

    @staticmethod
    @sync_to_async
    def create_message_sync(
        session: ChatSession,
        message_obj: dict,
        attachments: List[Dict] = None
    ) -> Message:
        """Create message (wrapped sync function)"""
        from django.db import transaction
        
        with transaction.atomic():
            # Get the last position
            last_message = Message.objects.filter(
                session=session
            ).order_by('-position').first()

            position = (last_message.position + 1) if last_message else 0

            # Create message
            message = Message.objects.create(
                id=message_obj['id'],
                session=session,
                role=message_obj['role'],
                content=message_obj.get('content') or "",
                parent_message_ids=message_obj['parent_message_ids'] or [],
                position=position,
                participant=message_obj.get('participant'),
                model=AIModel.objects.get(pk=message_obj['modelId']) if message_obj.get('modelId') else None,
                status='success' if message_obj['role'] == 'user' else 'streaming',
                attachments=attachments or [],
                audio_path=message_obj.get('audio_path'),
                image_path=message_obj.get('image_path'),
                doc_path=message_obj.get('doc_path'),
                language=message_obj.get('language'),
            )

            # Update parent messages
            if message_obj['parent_message_ids']:
                parent_messages = Message.objects.filter(id__in=message_obj['parent_message_ids'])
                for parent_msg in parent_messages:
                    if parent_msg.child_ids is None:
                        parent_msg.child_ids = []
                    parent_msg.child_ids.append(message.id)
                    parent_msg.save(update_fields=['child_ids'])

                # Create relations
                for parent_id in message_obj['parent_message_ids']:
                    MessageRelation.objects.create(
                        parent_id=parent_id,
                        child=message
                    )

            # Update session
            session.updated_at = timezone.now()
            session.save()

            return message

    @staticmethod
    @sync_to_async
    def get_message(message_id: str) -> Optional[Message]:
        """Get message by ID"""
        try:
            return Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            return None

    @staticmethod
    @sync_to_async
    def update_message(message_id: str, **updates):
        """Update message fields"""
        Message.objects.filter(id=message_id).update(**updates)

    @staticmethod
    @sync_to_async
    def get_session(session_id: str) -> Optional[ChatSession]:
        """Get session by ID"""
        try:
            return ChatSession.objects.select_related('model_a', 'model_b').get(id=session_id)
        except ChatSession.DoesNotExist:
            return None

    @staticmethod
    @sync_to_async
    def get_conversation_history(session: ChatSession, participant: Optional[str] = None) -> List[Dict]:
        """Get conversation history for a session"""
        messages = Message.objects.filter(
            session=session,
            role__in=['user', 'assistant']
        ).order_by('position')

        if participant:
            messages = messages.filter(participant=participant)

        history = []
        for msg in messages:
            history.append({
                "role": msg.role,
                "content": msg.content
            })

        return history

    @staticmethod
    def _send_message_update(message: Message, event_type: str):
        """Send WebSocket update (sync helper)"""
        channel_layer = get_channel_layer()
        if channel_layer:
            from asgiref.sync import async_to_sync
            async_to_sync(channel_layer.group_send)(
                f"session_{message.session.id}",
                {
                    'type': 'message_update',
                    'event_type': event_type,
                    'message': MessageSerializer(message).data
                }
            )

    # ========================================================================
    # ASYNC STREAMING METHODS
    # ========================================================================

    @staticmethod
    async def stream_assistant_message_async(
        session: ChatSession,
        user_message: Message,
        assistant_message: Message,
        model: Optional[AIModel] = None,
        participant: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncGenerator[Dict, None]:
        """Stream assistant response asynchronously"""
        
        # Determine model
        if not model:
            if session.mode == 'direct':
                model = session.model_a
            elif session.mode == 'compare':
                model = session.model_a if participant == 'a' else session.model_b

        if not model:
            yield {
                'type': 'error',
                'message_id': str(assistant_message.id),
                'error': 'No model specified'
            }
            return

        try:
            # Get conversation history
            messages = await MessageServiceAsync.get_conversation_history(session, participant)

            # System prompt
            system_prompt = "We will be rendering your response on a frontend. so please add spaces or indentation or nextline chars or bullet or numberings etc. suitably for code or the text. wherever required, and do not add any comments about this instruction in your response."

            # Stream from AI model
            content_chunks = []
            chunk_count = 0

            async for chunk in get_model_output_async(
                system_prompt=system_prompt,
                user_prompt=user_message.content,
                history=messages,
                model=model.model_code,
            ):
                content_chunks.append(chunk)
                chunk_count += 1
                
                # Update in-memory content
                full_content = ''.join(content_chunks)

                # Yield chunk to client
                yield {
                    'type': 'stream',
                    'message_id': str(assistant_message.id),
                    'chunk': chunk,
                    'content': full_content,
                    'participant': participant
                }

                # Periodically save to database and send WebSocket update
                if chunk_count % 10 == 0:
                    await MessageServiceAsync.update_message(
                        assistant_message.id,
                        content=full_content
                    )
                    
                    # Refresh message object for WebSocket
                    updated_msg = await MessageServiceAsync.get_message(assistant_message.id)
                    if updated_msg:
                        MessageServiceAsync._send_message_update(updated_msg, 'streaming')

            # Final update
            full_content = ''.join(content_chunks)
            await MessageServiceAsync.update_message(
                assistant_message.id,
                content=full_content,
                status='success',
                metadata={
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'completion_tokens': len(full_content.split())
                }
            )

            # Send final WebSocket update
            final_msg = await MessageServiceAsync.get_message(assistant_message.id)
            if final_msg:
                MessageServiceAsync._send_message_update(final_msg, 'completed')

            # Yield completion event
            yield {
                'type': 'complete',
                'message_id': str(assistant_message.id),
                'message': MessageSerializer(final_msg).data if final_msg else None,
                'participant': participant
            }

        except Exception as e:
            # Update message with error
            await MessageServiceAsync.update_message(
                assistant_message.id,
                status='failed',
                failure_reason=str(e)
            )

            error_msg = await MessageServiceAsync.get_message(assistant_message.id)
            if error_msg:
                MessageServiceAsync._send_message_update(error_msg, 'failed')

            yield {
                'type': 'error',
                'message_id': str(assistant_message.id),
                'error': str(e),
                'participant': participant
            }

    @staticmethod
    async def stream_dual_responses_async(
        session: ChatSession,
        user_message: Message,
        assistant_message_a: Message,
        assistant_message_b: Message,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncGenerator[Dict, None]:
        """
        Stream responses from both models concurrently
        Uses asyncio.Queue to merge streams
        """
        import asyncio

        # Create a queue to merge both streams
        queue = asyncio.Queue()

        # Task wrapper to put items in queue
        async def stream_to_queue(
            session, user_msg, assistant_msg, model, participant
        ):
            try:
                async for item in MessageServiceAsync.stream_assistant_message_async(
                    session=session,
                    user_message=user_msg,
                    assistant_message=assistant_msg,
                    model=model,
                    participant=participant,
                    temperature=temperature,
                    max_tokens=max_tokens
                ):
                    await queue.put(item)
            finally:
                # Signal this stream is done
                await queue.put({'stream_done': participant})

        # Start both streams concurrently
        task_a = asyncio.create_task(
            stream_to_queue(
                session, user_message, assistant_message_a,
                session.model_a, 'a'
            )
        )
        
        task_b = asyncio.create_task(
            stream_to_queue(
                session, user_message, assistant_message_b,
                session.model_b, 'b'
            )
        )

        # Track which streams are still active
        active_streams = {'a', 'b'}

        # Yield items as they arrive from either stream
        while active_streams:
            item = await queue.get()
            
            # Check if a stream finished
            if 'stream_done' in item:
                participant = item['stream_done']
                active_streams.discard(participant)
                continue
            
            # Yield the item
            yield item

        # Wait for both tasks to complete
        await asyncio.gather(task_a, task_b)

    @staticmethod
    async def regenerate_message_async(
        original_message: Message,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncGenerator[Dict, None]:
        """Regenerate an assistant message asynchronously"""
        
        # Get parent message
        if not original_message.parent_message_ids:
            yield {
                'type': 'error',
                'error': 'No parent message found'
            }
            return

        parent_id = original_message.parent_message_ids[0]
        parent_message = await MessageServiceAsync.get_message(parent_id)
        
        if not parent_message:
            yield {
                'type': 'error',
                'error': 'Parent message not found'
            }
            return

        # Create new assistant message
        import uuid
        new_message_obj = {
            'id': str(uuid.uuid4()),
            'role': 'assistant',
            'content': '',
            'parent_message_ids': [parent_id],
            'participant': original_message.participant,
            'modelId': str(original_message.model.id) if original_message.model else None
        }

        new_message = await MessageServiceAsync.create_message_sync(
            session=original_message.session,
            message_obj=new_message_obj
        )

        # Stream new response
        async for item in MessageServiceAsync.stream_assistant_message_async(
            session=original_message.session,
            user_message=parent_message,
            assistant_message=new_message,
            model=original_message.model,
            participant=original_message.participant,
            temperature=temperature,
            max_tokens=max_tokens
        ):
            yield item


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def create_and_stream_message(
    session_id: str,
    user_message_content: str,
    model_id: Optional[str] = None,
    participant: Optional[str] = None,
    **kwargs
) -> AsyncGenerator[Dict, None]:
    """
    High-level function: Create user message and stream assistant response
    
    Usage:
        async for chunk in create_and_stream_message(
            session_id="123",
            user_message_content="Hello",
            model_id="model_123"
        ):
            print(chunk)
    """
    import uuid
    
    # Get session
    session = await MessageServiceAsync.get_session(session_id)
    if not session:
        yield {'type': 'error', 'error': 'Session not found'}
        return

    # Create user message
    user_message_obj = {
        'id': str(uuid.uuid4()),
        'role': 'user',
        'content': user_message_content,
        'parent_message_ids': [],
        'participant': participant,
        'modelId': None
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
        'participant': participant,
        'modelId': model_id
    }
    
    assistant_message = await MessageServiceAsync.create_message_sync(
        session=session,
        message_obj=assistant_message_obj
    )

    # Determine model
    model = None
    if model_id:
        from ai_model.models import AIModel
        model = await sync_to_async(AIModel.objects.get)(id=model_id)

    # Stream response
    async for item in MessageServiceAsync.stream_assistant_message_async(
        session=session,
        user_message=user_message,
        assistant_message=assistant_message,
        model=model,
        participant=participant,
        **kwargs
    ):
        yield item
