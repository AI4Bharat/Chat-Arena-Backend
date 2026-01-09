from django.db.models import Count, Q
from user.models import User
from tenants.config import get_tenant_by_slug
from tenants.context import set_current_tenant, clear_current_tenant

def calculate_top_contributors(tenant_slug, language=None, arena_type=None):
    """
    Calculates top contributors based on chat sessions and feedback votes.
    Returns a list of dictionaries with user stats.
    """
    if not tenant_slug:
        raise ValueError("Tenant parameter is required")

    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant:
        raise ValueError("Invalid tenant")

    set_current_tenant(tenant)

    try:
        session_filters = Q()
        feedback_filters = Q()

        if arena_type:
            session_filters &= Q(chat_sessions__session_type__iexact=arena_type)
            feedback_filters &= Q(feedbacks__session__session_type__iexact=arena_type)
        
        if language:
            session_filters &= Q(chat_sessions__messages__language__iexact=language)
            feedback_filters &= Q(feedbacks__session__messages__language__iexact=language)

        users = User.objects.filter(is_active=True).annotate(
            chat_sessions_count=Count(
                'chat_sessions',
                filter=session_filters,
                distinct=True
            ),
            total_votes=Count(
                'feedbacks',
                filter=feedback_filters,
                distinct=True
            ),
            votes_direct=Count(
                'feedbacks',
                filter=feedback_filters & Q(feedbacks__session__mode='direct'),
                distinct=True
            ),
            votes_compare=Count(
                'feedbacks',
                filter=feedback_filters & Q(feedbacks__session__mode='compare'),
                distinct=True
            ),
            votes_random=Count(
                'feedbacks',
                filter=feedback_filters & Q(feedbacks__session__mode='random'),
                distinct=True
            )
        ).filter(
            Q(chat_sessions_count__gt=0) | Q(total_votes__gt=0)
        ).order_by('-total_votes', '-chat_sessions_count')

        results = []
        for user in users:
            results.append({
                'email': user.email,
                'display_name': user.display_name,
                'chat_sessions_count': user.chat_sessions_count,
                'total_votes': user.total_votes,
                'votes_breakdown': {
                    'Direct Chat': user.votes_direct,
                    'Comparison': user.votes_compare,
                    'Random': user.votes_random
                }
            })
        
        return results

    finally:
        clear_current_tenant()
