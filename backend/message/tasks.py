from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging
from message.models import Message
from message.utlis import MessageCache, MessageAnalyzer
from django.core.cache import cache
logger = logging.getLogger(__name__)


@shared_task
def cleanup_orphaned_messages():
    """Clean up messages with broken relationships"""
    
    # Find messages with parent_ids that don't exist
    orphaned_count = 0
    
    for message in Message.objects.exclude(parent_message_ids=[]):
        valid_parents = []
        for parent_id in message.parent_message_ids:
            if Message.objects.filter(id=parent_id).exists():
                valid_parents.append(parent_id)
            else:
                orphaned_count += 1
        
        if len(valid_parents) != len(message.parent_message_ids):
            message.parent_message_ids = valid_parents
            message.save()
    
    logger.info(f"Cleaned up {orphaned_count} orphaned parent references")
    return orphaned_count


@shared_task
def analyze_failed_messages():
    """Analyze failed messages and attempt to categorize failures"""
    
    failed_messages = Message.objects.filter(
        status='failed',
        created_at__gte=timezone.now() - timedelta(days=1)
    )
    
    failure_categories = {
        'timeout': 0,
        'rate_limit': 0,
        'invalid_request': 0,
        'model_error': 0,
        'unknown': 0
    }
    
    for message in failed_messages:
        reason = message.failure_reason or ''
        
        if 'timeout' in reason.lower():
            failure_categories['timeout'] += 1
        elif 'rate limit' in reason.lower() or '429' in reason:
            failure_categories['rate_limit'] += 1
        elif 'invalid' in reason.lower() or '400' in reason:
            failure_categories['invalid_request'] += 1
        elif 'model' in reason.lower() or '500' in reason:
            failure_categories['model_error'] += 1
        else:
            failure_categories['unknown'] += 1
    
    logger.info(f"Failed message analysis: {failure_categories}")
    
    return failure_categories


@shared_task
def calculate_message_metrics():
    """Calculate and cache message metrics"""
    
    # Get recent sessions with messages
    recent_messages = Message.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=1)
    ).values_list('session_id', flat=True).distinct()
    
    for session_id in recent_messages[:100]:  # Limit to 100 sessions
        messages = Message.objects.filter(
            session_id=session_id
        ).order_by('position')
        
        # Calculate metrics
        metrics = {
            'total_messages': messages.count(),
            'user_messages': messages.filter(role='user').count(),
            'assistant_messages': messages.filter(role='assistant').count(),
            'failed_messages': messages.filter(status='failed').count(),
            'avg_response_time': None,
            'conversation_analysis': MessageAnalyzer.analyze_conversation_quality(list(messages))
        }
        
        # Calculate average response time
        response_times = []
        last_user_time = None
        
        for msg in messages:
            if msg.role == 'user':
                last_user_time = msg.created_at
            elif msg.role == 'assistant' and last_user_time:
                response_time = (msg.created_at - last_user_time).total_seconds()
                response_times.append(response_time)
                last_user_time = None
        
        if response_times:
            metrics['avg_response_time'] = sum(response_times) / len(response_times)
        
        # Cache metrics
        cache_key = f"session_metrics:{session_id}"
        cache.set(cache_key, metrics, timeout=86400)  # 24 hours
    
    return f"Calculated metrics for {len(recent_messages)} sessions"


@shared_task
def detect_conversation_loops():
    """Detect potential conversation loops or repetitive patterns"""
    
    # Get recent conversations
    sessions_with_loops = []
    
    recent_sessions = Message.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=1)
    ).values_list('session_id', flat=True).distinct()[:50]
    
    for session_id in recent_sessions:
        messages = Message.objects.filter(
            session_id=session_id,
            role='user'
        ).order_by('position')
        
        # Check for similar messages
        for i in range(len(messages)):
            for j in range(i + 1, len(messages)):
                similarity = MessageAnalyzer.calculate_message_similarity(
                    messages[i].content,
                    messages[j].content
                )
                
                if similarity > 0.8:  # High similarity threshold
                    sessions_with_loops.append({
                        'session_id': session_id,
                        'message_1': str(messages[i].id),
                        'message_2': str(messages[j].id),
                        'similarity': similarity
                    })
                    break
    
    if sessions_with_loops:
        logger.warning(f"Detected potential loops in {len(sessions_with_loops)} sessions")
    
    return sessions_with_loops