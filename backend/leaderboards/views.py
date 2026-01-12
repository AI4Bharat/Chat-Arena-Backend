from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Q, Case, When, IntegerField
from .models import Leaderboard
from user.models import User
from chat_session.models import ChatSession
from feedback.models import Feedback
from tenants.config import get_tenant_by_slug
from tenants.context import set_current_tenant, clear_current_tenant
from .serializers import UserContributorSerializer

# Create your views here.
def get_leaderboard_api(request, arena_type):
    org_param = request.GET.get('org', 'ai4bharat')
    leaderboard_entry = Leaderboard.objects.filter(
        arena_type=arena_type,
        organization=org_param
    ).first()
    if leaderboard_entry:
        return JsonResponse(leaderboard_entry.leaderboard_json, safe=False)
    else:
        return JsonResponse(
            {"error": f"No leaderboard found for Type: {arena_type}, Org: {org_param}"}, 
            status=404
        )

from rest_framework.permissions import AllowAny

class TopContributorsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        tenant_slug = request.query_params.get('tenant')
        language = request.query_params.get('language')
        arena_type_param = request.query_params.get('arena_type')

        if not tenant_slug:
            return Response({"error": "Tenant parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        tenant = get_tenant_by_slug(tenant_slug)
        if not tenant:
            return Response({"error": "Invalid tenant"}, status=status.HTTP_404_NOT_FOUND)

        # Set the tenant context
        set_current_tenant(tenant)

        try:
            # Base filters for sessions and feedbacks
            session_filters = Q()
            feedback_filters = Q()

            if arena_type_param:
                session_filters &= Q(chat_sessions__session_type__iexact=arena_type_param)
                feedback_filters &= Q(feedbacks__session__session_type__iexact=arena_type_param)
            
            if language:
                # Filter by language in messages
                # Note: This checks if ANY message in the session/feedback-session has the language
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

            # Prepare data for serializer
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

            serializer = UserContributorSerializer(results, many=True)
            return Response(serializer.data)

        finally:
            # Always clear the tenant context
            clear_current_tenant()