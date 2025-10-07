from django.utils import timezone
from typing import List, Dict, Optional, AsyncGenerator, Generator
from django.db import transaction
from message.serializers import MessageSerializer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async
import asyncio
import json
from message.models import Message, MessageRelation
from chat_session.models import ChatSession
from ai_model.models import AIModel
from ai_model.services import AIModelService
from typing import List, Dict, Generator
from django.db.models import F
from ai_model.llm_interactions import get_model_output


class MessageService:
    """Service for managing messages"""
    
    @staticmethod
    def create_message(
        session: ChatSession,
        message_obj: dict,
        attachments: List[Dict] = None
    ) -> Message:
        """Create a user message"""
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
                content=message_obj['content'],
                parent_message_ids=message_obj['parent_message_ids'] or [],
                position=position,
                participant=message_obj.get('participant'),
                model = AIModel.objects.get(pk=message_obj['modelId']) if message_obj.get('modelId') else None,
                status='success' if message_obj['role'] == 'user' else 'streaming',
                attachments=attachments or []
            )
            
            # Update parent messages
            if message_obj['parent_message_ids']:
                # Fetch parent messages and update their child_ids
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
            
            # Send WebSocket update
            MessageService._send_message_update(message, 'created')
            
            return message
    
    @staticmethod
    def stream_assistant_message(
        session: ChatSession,
        user_message: Message,
        assistant_message: Message,
        model: AIModel = None,
        participant: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> Generator[Dict, None, None]:
        """Stream assistant response"""
        # Determine model
        if not model:
            if session.mode == 'direct':
                model = session.model_a
            elif session.mode == 'compare':
                model = session.model_a if participant == 'a' else session.model_b

        if not model:
            raise ValueError("No model specified")
        
        # Create assistant message placeholder
        # assistant_message = await sync_to_async(Message.objects.create)(
        #     session=session,
        #     role='assistant',
        #     content='',
        #     model=model,
        #     parent_message_ids=[user_message.id],
        #     position=user_message.position + 1,
        #     participant=participant,
        #     status='streaming',
        #     metadata={
        #         'temperature': temperature,
        #         'max_tokens': max_tokens
        #     }
        # )
        
        # Update parent
        # await sync_to_async(MessageService._update_parent_child_ids)(
        #     user_message.id, 
        #     assistant_message.id
        # )

        try:
            # Get conversation history
            messages = MessageService._get_conversation_history(session)
            
            # Stream from AI model
            ai_service = AIModelService()
            content_chunks = []
            
            for chunk in get_model_output(
                system_prompt="We will be rendering your response on a frontend. so please add spaces or indentation or nextline chars or bullet or numberings etc. suitably for code or the text. wherever required, and do not add any comments about this instruction in your response.",
                user_prompt=user_message.content,
                history=messages,
                model="google/gemma-3-12b-it",
            ):
                content_chunks.append(chunk)
                assistant_message.content = ''.join(content_chunks)
                
                # Yield update
                yield {
                    'type': 'stream',
                    'message_id': str(assistant_message.id),
                    'chunk': chunk,
                    'content': assistant_message.content
                }
                
                # Send WebSocket update periodically
                if len(content_chunks) % 10 == 0:
                    MessageService._send_message_update(
                        assistant_message, 'streaming'
                    )
            
            # Final update
            assistant_message.status = 'success'
            assistant_message.metadata['completion_tokens'] = len(''.join(content_chunks).split())
            assistant_message.save()
            
            # Send final WebSocket update
            MessageService._send_message_update(
                assistant_message, 'completed'
            )
            
            yield {
                'type': 'complete',
                'message_id': str(assistant_message.id),
                'message': MessageSerializer(assistant_message).data
            }
            
        except Exception as e:
            # Update message with error
            assistant_message.status = 'failed'
            assistant_message.failure_reason = str(e)
            assistant_message.save()
            
            yield {
                'type': 'error',
                'message_id': str(assistant_message.id),
                'error': str(e)
            }
    
    @staticmethod
    def create_branch(
        parent_message: Message,
        content: str,
        branch_type: str = 'alternative'
    ) -> Message:
        """Create a branch from an existing message"""
        with transaction.atomic():
            # Create new message at same position level
            branch_message = Message.objects.create(
                session=parent_message.session,
                role='user',
                content=content,
                parent_message_ids=parent_message.parent_message_ids,
                position=parent_message.position,
                status='success',
                metadata={
                    'branch_type': branch_type,
                    'branched_from': str(parent_message.id)
                }
            )
            
            # Update parent's children
            for parent_id in parent_message.parent_message_ids:
                parent = Message.objects.get(id=parent_id)
                if branch_message.id not in parent.child_ids:
                    parent.child_ids.append(branch_message.id)
                    parent.save()
            
            # Create relations
            for parent_id in parent_message.parent_message_ids:
                MessageRelation.objects.create(
                    parent_id=parent_id,
                    child=branch_message,
                    relation_type='branch'
                )
            
            return branch_message
    
    @staticmethod
    def regenerate_message(
        message: Message,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        use_different_model: bool = False,
        new_model_id: Optional[str] = None
    ) -> Message:
        """Regenerate an assistant message"""
        if message.role != 'assistant':
            raise ValueError("Can only regenerate assistant messages")
        
        with transaction.atomic():
            # Determine model
            if use_different_model and new_model_id:
                model = AIModel.objects.get(id=new_model_id)
            else:
                model = message.model

            # Create new message as alternative
            new_message = Message.objects.create(
                session=message.session,
                role='assistant',
                content='',
                model=model,
                parent_message_ids=message.parent_message_ids,
                position=message.position,
                participant=message.participant,
                status='pending',
                metadata={
                    'regenerated_from': str(message.id),
                    'temperature': temperature,
                    'max_tokens': max_tokens
                }
            )
            
            # Update parent's children to include new message
            for parent_id in message.parent_message_ids:
                parent = Message.objects.get(id=parent_id)
                if new_message.id not in parent.child_ids:
                    parent.child_ids.append(new_message.id)
                    parent.save()
            
            return new_message
    
    @staticmethod
    def _get_conversation_history(session: ChatSession, participant=None) -> List[Dict]:
        """Get conversation history for AI context"""
        messages_query = Message.objects.filter(
            session=session,
            status='success'
        )
        
        if participant is not None:
            other_participation = 'b' if participant == 'a' else 'a'
            messages_query = messages_query.exclude(participant=other_participation)
        
        
        messages = messages_query.order_by('position')
        
        history = []
        for msg in messages:
            history.append({
                'role': msg.role,
                'content': msg.content
            })
        
        return history
    
    @staticmethod
    def _update_parent_child_ids(parent_id: str, child_id: str):
        """Update parent message's child IDs"""
        parent = Message.objects.get(id=parent_id)
        if child_id not in parent.child_ids:
            parent.child_ids.append(child_id)
            parent.save()
    
    @staticmethod
    def _send_message_update(message: Message, action: str):
        """Send message update via WebSocket"""
        channel_layer = get_channel_layer()
        
        async_to_sync(channel_layer.group_send)(
            f"session_{message.session_id}",
            {
                'type': 'message_update',
                'message': MessageSerializer(message).data,
                'action': action
            }
        )
    
    @staticmethod
    def get_message_tree(root_message_id: str) -> Dict:
        """Get complete message tree from a root message"""
        root = Message.objects.get(id=root_message_id)
        return MessageService._build_tree(root)
    
    @staticmethod
    def _build_tree(message: Message) -> Dict:
        """Recursively build message tree"""
        tree = {
            'id': str(message.id),
            'role': message.role,
            'content': message.content,
            'model': message.model.display_name if message.model else None,
            'participant': message.participant,
            'created_at': message.created_at.isoformat(),
            'children': []
        }
        
        if message.child_ids:
            children = Message.objects.filter(id__in=message.child_ids).order_by('created_at')
            for child in children:
                tree['children'].append(MessageService._build_tree(child))
        
        return tree


class MessageComparisonService:
    """Service for handling message comparisons in compare mode"""
    
    @staticmethod
    async def stream_dual_responses(
        session: ChatSession,
        user_message: Message,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncGenerator[Dict, None]:
        """Stream responses from both models simultaneously"""
        if session.mode != 'compare':
            raise ValueError("Session must be in compare mode")
        
        # Create tasks for both models
        task_a = MessageService.stream_assistant_message(
            session=session,
            user_message=user_message,
            model=session.model_a,
            participant='a',
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        task_b = MessageService.stream_assistant_message(
            session=session,
            user_message=user_message,
            model=session.model_b,
            participant='b',
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Stream both responses
        async def stream_wrapper(stream, label):
            async for item in stream:
                yield {**item, 'participant': label}
        
        # Merge streams
        stream_a = stream_wrapper(task_a, 'a')
        stream_b = stream_wrapper(task_b, 'b')
        
        # Create queue for merging
        queue = asyncio.Queue()
        
        async def queue_stream(stream):
            try:
                async for item in stream:
                    await queue.put(item)
            finally:
                await queue.put(None)
        
        # Start both streams
        asyncio.create_task(queue_stream(stream_a))
        asyncio.create_task(queue_stream(stream_b))
        
        # Yield from queue
        completed = 0
        while completed < 2:
            item = await queue.get()
            if item is None:
                completed += 1
            else:
                yield item
