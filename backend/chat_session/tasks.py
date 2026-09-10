from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging
from chat_session.models import ChatSession
from message.models import Message
from chat_session.services import ChatSessionService
from django.core.mail import EmailMessage
from chat_session.utils import SessionAnalyzer
from django.core.cache import cache
import zipfile
import io

from tenants.context import tenant_aware_task

logger = logging.getLogger(__name__)


@shared_task
@tenant_aware_task
def cleanup_expired_sessions():
    """Clean up expired anonymous sessions"""
    
    count = ChatSessionService.cleanup_expired_sessions()
    logger.info(f"Cleaned up {count} expired sessions")
    return count


@shared_task
@tenant_aware_task
def generate_session_titles():
    """Generate titles for untitled sessions based on content"""
    
    untitled_sessions = ChatSession.objects.filter(
        title__isnull=True,
        created_at__gte=timezone.now() - timedelta(days=1)
    )
    
    for session in untitled_sessions:
        # Get first user message
        first_message = Message.objects.filter(
            session=session,
            role='user'
        ).order_by('position').first()
        
        if first_message:
            # Generate title from first message
            title = first_message.content[:50]
            if len(first_message.content) > 50:
                title += "..."
            
            session.title = title
            session.save()
    
    return f"Generated titles for {untitled_sessions.count()} sessions"


@shared_task
@tenant_aware_task
def calculate_session_analytics():
    """Calculate analytics for active sessions"""
    
    # Get sessions with recent activity
    recent_sessions = ChatSession.objects.filter(
        updated_at__gte=timezone.now() - timedelta(hours=24)
    ).select_related('model_a', 'model_b')[:100]
    
    for session in recent_sessions:
        # Calculate and cache analytics
        analytics = SessionAnalyzer.analyze_conversation_flow(session)
        
        cache_key = f"session_analytics:{session.id}"
        cache.set(cache_key, analytics, timeout=86400)  # 24 hours
    
    return f"Calculated analytics for {recent_sessions.count()} sessions"


@shared_task
def export_session_batch(session_ids: list, user_email: str, format: str = 'json', tenant_slug: str = None):
    """Export multiple sessions and send to user"""
    if tenant_slug:
        from tenants.config import get_tenant_by_slug
        from tenants.context import set_current_tenant
        tenant = get_tenant_by_slug(tenant_slug)
        if tenant:
            set_current_tenant(tenant)

    try:
        sessions = ChatSession.objects.filter(id__in=session_ids)

        if not sessions:
            return "No sessions found"

        # Create zip file in memory
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for session in sessions:
                content, _ = ChatSessionService.export_session(
                    session=session,
                    format=format,
                    include_metadata=True,
                    include_timestamps=True
                )

                filename = f"{session.title or 'untitled'}_{session.id}.{format}"
                zip_file.writestr(filename, content)

        # Send email with attachment
        email = EmailMessage(
            subject='Your Chat Sessions Export',
            body=f'Please find attached your exported {len(sessions)} chat sessions.',
            to=[user_email]
        )

        zip_buffer.seek(0)
        email.attach(
            f'chat_sessions_export_{timezone.now().strftime("%Y%m%d")}.zip',
            zip_buffer.read(),
            'application/zip'
        )

        email.send()

        return f"Exported {len(sessions)} sessions and sent to {user_email}"
    finally:
        if tenant_slug:
            from tenants.context import clear_current_tenant
            clear_current_tenant()
