from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Count, Avg, Q
from datetime import timedelta, datetime
from django.utils import timezone

from feedback.models import Feedback
from feedback.serializers import (
    FeedbackSerializer, FeedbackCreateSerializer,
    BulkFeedbackSerializer, SessionFeedbackSummarySerializer,
    ModelFeedbackStatsSerializer
)
from feedback.services import FeedbackService, FeedbackAnalyticsService
from feedback.analytics import FeedbackAnalyzer
from feedback.permissions import IsFeedbackOwner
from user.authentication import FirebaseAuthentication, AnonymousTokenAuthentication
from chat_session.models import ChatSession
from ai_model.models import AIModel


class FeedbackViewSet(viewsets.ModelViewSet):
    """ViewSet for feedback management"""
    authentication_classes = [FirebaseAuthentication, AnonymousTokenAuthentication]
    permission_classes = [IsAuthenticated, IsFeedbackOwner]
    queryset = Feedback.objects.select_related('user', 'session', 'message', 'preferred_model')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return FeedbackCreateSerializer
        elif self.action == 'bulk_create':
            return BulkFeedbackSerializer
        return FeedbackSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Users can see their own feedback and feedback on public sessions
        queryset = queryset.filter(
            Q(user=user) | Q(session__is_public=True)
        )
        
        # Filter by session
        session_id = self.request.query_params.get('session_id')
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        
        # Filter by type
        feedback_type = self.request.query_params.get('type')
        if feedback_type:
            queryset = queryset.filter(feedback_type=feedback_type)
        
        # Filter by model
        model_id = self.request.query_params.get('model_id')
        if model_id:
            queryset = queryset.filter(
                Q(message__model_id=model_id) |
                Q(preferred_model_id=model_id)
            )
        
        return queryset.order_by('-created_at')
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Create multiple feedbacks at once"""
        serializer = BulkFeedbackSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        feedbacks = serializer.save()
        
        return Response(
            FeedbackSerializer(feedbacks, many=True).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['get'])
    def session_summary(self, request):
        """Get feedback summary for a session"""
        try:
            session_id = request.query_params.get('session_id')
            if not session_id:
                return Response(
                    {'error': 'session_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            session = get_object_or_404(ChatSession, id=session_id)
            
            # Check permissions
            if session.user != request.user and not session.is_public:
                return Response(
                    {'error': 'You do not have access to this session'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            summary = FeedbackService.get_session_feedback_summary(session)
            
            return Response(SessionFeedbackSummarySerializer(summary).data)
        except Exception as e:
            from common.error_logging import log_and_respond, create_log_context
            log_context = create_log_context(request, session_id=session_id if 'session_id' in locals() else None)
            return log_and_respond(
                e,
                endpoint='/feedback/session_summary/',
                log_context=log_context
            )
    
    @action(detail=False, methods=['get'])
    def my_stats(self, request):
        """Get current user's feedback statistics"""
        try:
            time_period = request.query_params.get('period', '30')
            
            try:
                days = int(time_period)
                period = timedelta(days=days)
            except ValueError as e:
                # Log validation error with detailed context
                from common.error_logging import log_and_respond, create_log_context
                log_context = create_log_context(request)
                return log_and_respond(
                    e,
                    endpoint='/feedback/my_stats/',
                    log_context=log_context,
                    custom_message=f"Invalid time period format: '{time_period}'. Please provide a valid number of days."
                )
            
            stats = FeedbackAnalyzer.analyze_user_preferences(
                request.user,
                time_period=period
            )
            
            return Response(stats)
        except Exception as e:
            # Log unexpected errors
            from common.error_logging import log_and_respond, create_log_context
            log_context = create_log_context(request)
            return log_and_respond(
                e,
                endpoint='/feedback/my_stats/',
                log_context=log_context
            )
    
    @action(detail=False, methods=['get'])
    def model_comparison(self, request):
        """Get head-to-head model comparison stats"""
        model_a_id = request.query_params.get('model_a_id')
        model_b_id = request.query_params.get('model_b_id')
        
        if not model_a_id or not model_b_id:
            return Response(
                {'error': 'Both model_a_id and model_b_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        model_a = get_object_or_404(AIModel, id=model_a_id)
        model_b = get_object_or_404(AIModel, id=model_b_id)
        
        stats = FeedbackService.calculate_model_comparison_stats(model_a, model_b)
        
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def trending_categories(self, request):
        """Get trending feedback categories"""
        days = int(request.query_params.get('days', 7))
        trending = FeedbackAnalyticsService.get_trending_feedback_categories(days)
        
        return Response(trending)


class ModelFeedbackView(views.APIView):
    """View for model-specific feedback data"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, model_id):
        """Get feedback statistics for a specific model"""
        model = get_object_or_404(AIModel, id=model_id)
        
        # Time period filter
        period_param = request.query_params.get('period', '30')
        try:
            days = int(period_param)
            time_period = timedelta(days=days) if days > 0 else None
        except ValueError:
            time_period = None
        
        stats = FeedbackService.get_model_feedback_stats(model, time_period)
        
        return Response(ModelFeedbackStatsSerializer(stats).data)


class FeedbackReportView(views.APIView):
    """Generate feedback reports"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Generate feedback report for a date range"""
        
        # Parse date parameters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date or not end_date:
            # Default to last 30 days
            end = timezone.now()
            start = end - timedelta(days=30)
        else:
            try:
                start = datetime.fromisoformat(start_date)
                end = datetime.fromisoformat(end_date)
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use ISO format'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Ensure dates are timezone-aware
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
        if timezone.is_naive(end):
            end = timezone.make_aware(end)
        
        report = FeedbackAnalyzer.generate_feedback_report(start, end)
        
        return Response(report)