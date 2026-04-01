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
    def create_session_with_random_models(user, mode: str = 'random', metadata: Dict = None, session_type: str = None) -> ChatSession:
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
        include_messages: bool = True,
        new_title: Optional[str] = None
    ) -> ChatSession:
        """
        Duplicate / fork a chat session safely.

        Used for:
        - user duplication
        - shared session continuation
        """
        with transaction.atomic():
            if session.deleted_at is not None:
                raise ValueError("Cannot clone a deleted session.")

            # Create new session
            new_session = ChatSession.objects.create(
                user=user,
                mode=session.mode,
                title=new_title or session.title or "Continued Chat",
                model_a=session.model_a,
                model_b=session.model_b,
                session_type=session.session_type,
                metadata={
                    **(session.metadata or {}),
                    "duplicated_from": str(session.id),
                    "duplicated_at": timezone.now().isoformat(),
                    "fork_type": "shared_continue"
                },
                meta_stats_json=session.meta_stats_json,
                is_public=False,
                share_token=None,
                is_pinned=False,
            )

            if not include_messages:
                return new_session

            original_messages = list(
                session.messages.select_related("model")
                .order_by("position", "created_at")
            )

            old_to_new_id_map = {}
            cloned_messages = []

            # First pass → clone messages
            for msg in original_messages:
                new_msg = Message(
                    session=new_session,
                    role=msg.role,
                    content=msg.content,
                    audio_path=msg.audio_path,
                    image_path=msg.image_path,
                    doc_path=msg.doc_path,
                    model=msg.model,
                    position=msg.position,
                    participant=msg.participant,
                    status="success" if msg.status != "failed" else "failed",
                    failure_reason=msg.failure_reason,
                    attachments=msg.attachments,
                    metadata={
                        **(msg.metadata or {}),
                        "duplicated_from": str(msg.id)
                    },
                    feedback=msg.feedback,
                    has_detailed_feedback=msg.has_detailed_feedback,
                    meta_stats_json=msg.meta_stats_json,
                    language=msg.language,
                    latency_ms=msg.latency_ms,
                    parent_message_ids=[],
                    child_ids=[]
                )

                cloned_messages.append(new_msg)
                old_to_new_id_map[str(msg.id)] = new_msg

            # Bulk insert
            Message.objects.bulk_create(cloned_messages)

            # Second pass → restore parent-child relationships
            refreshed_cloned_messages = list(
                Message.objects.filter(session=new_session)
                .order_by("position", "created_at")
            )

            old_ids = [str(msg.id) for msg in original_messages]

            for old_msg, new_msg in zip(original_messages, refreshed_cloned_messages):
                new_parent_ids = [
                    refreshed_cloned_messages[old_ids.index(str(pid))].id
                    for pid in (old_msg.parent_message_ids or [])
                    if str(pid) in old_ids
                ]

                new_child_ids = [
                    refreshed_cloned_messages[old_ids.index(str(cid))].id
                    for cid in (old_msg.child_ids or [])
                    if str(cid) in old_ids
                ]

                new_msg.parent_message_ids = new_parent_ids
                new_msg.child_ids = new_child_ids

            Message.objects.bulk_update(
                refreshed_cloned_messages,
                ["parent_message_ids", "child_ids"]
            )

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