from typing import List, Dict, Optional, Tuple
from django.db import transaction
from django.utils import timezone
import random
import json

from chat_session.models import ChatSession
from ai_model.models import AIModel
from ai_model.utils import ModelSelector
from message.models import Message
from feedback.models import Feedback
from django.db.models import Avg, Count, Q, Max
from ai_model.utils import count_tokens, ModelCostCalculator
from datetime import timedelta


class ChatSessionService:
    """Service for managing chat sessions"""
    
    @staticmethod
    def create_session_with_random_models(user, mode: str = 'random', metadata: Dict = None, session_type: str = None, language: str = None) -> ChatSession:
        """Create a session with randomly selected models"""
        
        # Check metadata for multimodal requirements
        requires_multimodal = False
        if metadata:
            requires_multimodal = metadata.get('has_image', False) or metadata.get('has_audio', False) or metadata.get('has_document', False)

        try:
            model_a, model_b = ModelSelector.get_random_models_for_comparison(
                model_type=session_type,
                requires_multimodal=requires_multimodal,
                mode=mode,
                language=language
            )
        except ValueError as e:
            raise ValueError("Not enough active models for random comparison")
        
        session = ChatSession.objects.create(
            user=user,
            mode=mode,
            model_a=model_a,
            model_b=model_b,
            metadata=metadata or {},
            session_type=session_type,
        )
        
        # Add random selection info to metadata
        session.metadata['random_selection'] = {
            'selected_at': timezone.now().isoformat(),
            'selection_method': 'random'
        }
        session.save()
        
        return session
    
    @staticmethod
    def duplicate_session(
        session: ChatSession, 
        user,
        include_messages: bool = False,
        new_title: Optional[str] = None
    ) -> ChatSession:
        """Duplicate a chat session"""
        # Create new session
        new_session = ChatSession.objects.create(
            user=user,
            mode=session.mode,
            title=new_title or f"Copy of {session.title or 'Untitled'}",
            model_a=session.model_a,
            model_b=session.model_b,
            metadata={
                **session.metadata,
                'duplicated_from': str(session.id),
                'duplicated_at': timezone.now().isoformat()
            }
        )
        
        # Duplicate messages if requested
        if include_messages:
            messages = session.messages.order_by('position')
            
            # Create a mapping of old IDs to new IDs for parent-child relationships
            id_mapping = {}
            
            for message in messages:
                old_id = message.id
                
                # Create new message
                new_message = Message(
                    session=new_session,
                    role=message.role,
                    content=message.content,
                    model=message.model,
                    position=message.position,
                    participant=message.participant,
                    status='success',  # Set as success since it's a copy
                    attachments=message.attachments,
                    metadata={
                        **message.metadata,
                        'duplicated_from': str(old_id)
                    }
                )
                
                # Map parent IDs
                if message.parent_message_ids:
                    new_message.parent_message_ids = [
                        id_mapping.get(str(pid), pid) 
                        for pid in message.parent_message_ids
                    ]
                
                new_message.save()
                id_mapping[str(old_id)] = new_message.id
                
                # Update child IDs for previously saved messages
                for parent_id in new_message.parent_message_ids:
                    parent_msg = Message.objects.filter(id=parent_id).first()
                    if parent_msg and new_message.id not in parent_msg.child_ids:
                        parent_msg.child_ids.append(new_message.id)
                        parent_msg.save()
        
        return new_session
    
    @staticmethod
    def export_session(
        session: ChatSession,
        format: str = 'json',
        include_metadata: bool = False,
        include_timestamps: bool = True
    ) -> Tuple[str, str]:
        """
        Export session data in various formats
        Returns: (content, content_type)
        """
        messages = session.messages.order_by('position')
        
        if format == 'json':
            data = {
                'session': {
                    'id': str(session.id),
                    'mode': session.mode,
                    'title': session.title,
                    'created_at': session.created_at.isoformat() if include_timestamps else None,
                    'model_a': session.model_a.display_name if session.model_a else None,
                    'model_b': session.model_b.display_name if session.model_b else None,
                },
                'messages': []
            }
            
            if include_metadata:
                data['session']['metadata'] = session.metadata
            
            for msg in messages:
                msg_data = {
                    'role': msg.role,
                    'content': msg.content,
                    'model': msg.model.display_name if msg.model else None,
                    'participant': msg.participant
                }
                
                if include_timestamps:
                    msg_data['created_at'] = msg.created_at.isoformat()
                
                if include_metadata:
                    msg_data['metadata'] = msg.metadata
                
                data['messages'].append(msg_data)
            
            return json.dumps(data, indent=2), 'application/json'
        
        elif format == 'markdown':
            lines = [
                f"# {session.title or 'Chat Session'}",
                f"\n**Mode**: {session.get_mode_display()}",
            ]
            
            if session.model_a:
                lines.append(f"**Model A**: {session.model_a.display_name}")
            if session.model_b:
                lines.append(f"**Model B**: {session.model_b.display_name}")
            
            if include_timestamps:
                lines.append(f"**Created**: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            
            lines.append("\n---\n")
            
            for msg in messages:
                if msg.role == 'user':
                    lines.append(f"### User\n{msg.content}\n")
                else:
                    model_name = msg.model.display_name if msg.model else "Assistant"
                    if session.mode == 'compare' and msg.participant:
                        model_name = f"{model_name} ({msg.participant.upper()})"
                    lines.append(f"### {model_name}\n{msg.content}\n")
                
                if include_timestamps:
                    lines.append(f"*{msg.created_at.strftime('%H:%M:%S')}*\n")
                
                lines.append("")
            
            return '\n'.join(lines), 'text/markdown'
        
        elif format == 'txt':
            lines = [
                f"{session.title or 'Chat Session'}",
                f"Mode: {session.get_mode_display()}",
                "=" * 50,
                ""
            ]
            
            for msg in messages:
                if msg.role == 'user':
                    lines.append(f"USER: {msg.content}")
                else:
                    model_name = msg.model.display_name if msg.model else "ASSISTANT"
                    if session.mode == 'compare' and msg.participant:
                        model_name = f"{model_name} ({msg.participant.upper()})"
                    lines.append(f"{model_name}: {msg.content}")
                
                if include_timestamps:
                    lines.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}]")
                
                lines.append("")
            
            return '\n'.join(lines), 'text/plain'
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    @staticmethod
    def get_session_statistics(session: ChatSession) -> Dict:
        """Get detailed statistics for a session"""
        
        messages = session.messages.all()
        
        stats = {
            'duration': {
                'total_seconds': None,
                'formatted': None
            },
            'messages': {
                'total': messages.count(),
                'by_role': messages.values('role').annotate(count=Count('id')),
                'by_model': {}
            },
            'tokens': {
                'total_input': 0,
                'total_output': 0,
                'estimated_cost': 0
            },
            'feedback': {
                'ratings_count': 0,
                'average_rating': None,
                'preferences': {}
            }
        }
        
        # Calculate duration
        if messages.exists():
            first_msg = messages.order_by('created_at').first()
            last_msg = messages.order_by('created_at').last()
            duration = last_msg.created_at - first_msg.created_at
            stats['duration']['total_seconds'] = duration.total_seconds()
            stats['duration']['formatted'] = str(duration).split('.')[0]
        
        # Messages by model
        if session.mode in ['direct', 'compare']:
            for model in [session.model_a, session.model_b]:
                if model:
                    model_messages = messages.filter(model=model)
                    stats['messages']['by_model'][model.display_name] = model_messages.count()
        
        # Token usage and cost estimation        
        for msg in messages:
            tokens = count_tokens(msg.content)
            if msg.role == 'user':
                stats['tokens']['total_input'] += tokens
            else:
                stats['tokens']['total_output'] += tokens
                
                # Estimate cost if model is available
                if msg.model:
                    cost_info = ModelCostCalculator.estimate_cost(
                        msg.model.model_code,
                        0,  # Input tokens already counted
                        tokens
                    )
                    stats['tokens']['estimated_cost'] += cost_info['total_cost']
        
        # Feedback statistics
        feedback = Feedback.objects.filter(session=session)
        
        ratings = feedback.filter(
            feedback_type='rating',
            rating__isnull=False
        )
        
        if ratings.exists():
            stats['feedback']['ratings_count'] = ratings.count()
            stats['feedback']['average_rating'] = ratings.aggregate(
                avg=Avg('rating')
            )['avg']
        
        # Preference statistics for compare mode
        if session.mode == 'compare':
            preferences = feedback.filter(feedback_type='preference')
            
            for model in [session.model_a, session.model_b]:
                if model:
                    pref_count = preferences.filter(preferred_model=model).count()
                    stats['feedback']['preferences'][model.display_name] = pref_count
        
        return stats
    
    @staticmethod
    def cleanup_expired_sessions():
        """Clean up expired anonymous user sessions"""
        expired_sessions = ChatSession.objects.filter(
            expires_at__lt=timezone.now()
        )
        
        count = expired_sessions.count()
        expired_sessions.delete()
        
        return count
    
    @staticmethod
    def get_trending_sessions(limit: int = 10) -> List[ChatSession]:
        """Get trending public sessions based on recent activity"""
        
        # Look at sessions with activity in the last 7 days
        recent_date = timezone.now() - timedelta(days=7)
        
        trending = ChatSession.objects.filter(
            is_public=True,
            updated_at__gte=recent_date
        ).annotate(
            message_count=Count('messages'),
            feedback_count=Count('feedbacks'),
            last_activity=Max('messages__created_at')
        ).order_by(
            '-feedback_count',
            '-message_count',
            '-last_activity'
        )[:limit]
        
        return trending