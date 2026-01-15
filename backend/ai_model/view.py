from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django.http import StreamingHttpResponse
from django.db.models import Q, Count, Avg
import json
import asyncio

from model_metrics.models import AIModel, ModelMetric
from ai_model.serializers import (
    AIModelSerializer, AIModelListSerializer, ModelMetricSerializer,
    ModelComparisonSerializer, ModelTestSerializer, ModelCapabilitySerializer
)
from ai_model.services import AIModelService
from user.authentication import FirebaseAuthentication, AnonymousTokenAuthentication
from message.models import Message
from feedback.models import Feedback

class AIModelViewSet(viewsets.ModelViewSet):
    """ViewSet for AI Model management"""
    queryset = AIModel.objects.all()
    authentication_classes = [FirebaseAuthentication, AnonymousTokenAuthentication]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return AIModelListSerializer
        elif self.action == 'test':
            return ModelTestSerializer
        elif self.action == 'compare':
            return ModelComparisonSerializer
        elif self.action == 'filtered_by_type':
            return AIModelListSerializer
        return AIModelSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by active status
        # if not self.request.user.is_staff:
        queryset = queryset.filter(is_active=True)
        
        # Exclude academic-only TTS models (ElevenLabs and IndicParlerTTS) unless:
        # 1. Mode is academic
        
        mode = self.request.query_params.get('mode')
        
        if mode != 'academic':
            queryset = queryset.exclude(
                model_code__in=['elevenlabs', 'indicparlertts']
            )
        
        # Filter by provider
        provider = self.request.query_params.get('provider')
        if provider:
            queryset = queryset.filter(provider=provider)
        
        # Filter by capabilities
        capabilities = self.request.query_params.getlist('capability')
        if capabilities:
            for capability in capabilities:
                queryset = queryset.filter(capabilities__contains=[capability])
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(display_name__icontains=search) |
                Q(description__icontains=search) |
                Q(model_code__icontains=search)
            )
        
        return queryset.order_by('-release_date', 'provider', 'display_name')
    
    @action(detail=False, methods=['get'], url_path='type')
    def filtered_by_type(self, request):
        """
        Returns models filtered by model_type
        """
        model_type = request.query_params.get('model_type')
        mode = request.query_params.get('mode')
        qs = self.get_queryset()

        if model_type:
            qs = qs.filter(model_type=model_type)
        
        if mode != 'academic':
            qs = qs.exclude(model_code__in=['elevenlabs', 'indicparlertts'])

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def providers(self, request):
        """Get list of available providers"""
        providers = AIModel.objects.filter(
            is_active=True
        ).values_list('provider', flat=True).distinct()
        
        provider_info = []
        for provider in providers:
            models = AIModel.objects.filter(provider=provider, is_active=True)
            provider_info.append({
                'name': provider,
                'display_name': provider.title(),
                'model_count': models.count(),
                'models': AIModelListSerializer(models, many=True).data
            })
        
        return Response(provider_info)
    
    @action(detail=False, methods=['get'])
    def capabilities(self, request):
        """Get all available capabilities"""
        all_capabilities = set()
        
        for model in AIModel.objects.filter(is_active=True):
            all_capabilities.update(model.capabilities or [])
        
        capability_info = []
        for cap in sorted(all_capabilities):
            models_with_cap = AIModel.objects.filter(
                is_active=True,
                capabilities__contains=[cap]
            ).count()
            
            capability_info.append({
                'name': cap,
                'display_name': cap.replace('_', ' ').title(),
                'model_count': models_with_cap
            })
        
        return Response(capability_info)
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test a model with a prompt"""
        model = self.get_object()
        serializer = ModelTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = AIModelService()
        messages = [
            {'role': 'user', 'content': serializer.validated_data['prompt']}
        ]
        
        if serializer.validated_data['stream']:
            # Return streaming response
            async def generate():
                async for chunk in service.stream_completion(
                    model=model,
                    messages=messages,
                    temperature=serializer.validated_data['temperature'],
                    max_tokens=serializer.validated_data['max_tokens']
                ):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                yield "data: [DONE]\n\n"
            
            response = StreamingHttpResponse(
                asyncio.run(generate()),
                content_type='text/event-stream'
            )
            response['Cache-Control'] = 'no-cache'
            return response
        else:
            # Return non-streaming response
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(
                service.get_completion(
                    model=model,
                    messages=messages,
                    temperature=serializer.validated_data['temperature'],
                    max_tokens=serializer.validated_data['max_tokens']
                )
            )
            
            return Response({'result': result})
    
    @action(detail=True, methods=['get'])
    def validate(self, request, pk=None):
        """Validate model configuration"""
        model = self.get_object()
        service = AIModelService()
        
        validation_result = service.validate_model_configuration(model)
        return Response(validation_result)
    
    @action(detail=False, methods=['post'])
    def compare(self, request):
        """Compare two models"""
        serializer = ModelComparisonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        model_a = serializer.validated_data['model_a']
        model_b = serializer.validated_data['model_b']
        
        # Create streaming response for both models
        async def generate():
            service = AIModelService()
            async for item in service.compare_models(
                model_a=model_a,
                model_b=model_b,
                messages=serializer.validated_data['messages'],
                temperature=serializer.validated_data['temperature'],
                max_tokens=serializer.validated_data['max_tokens']
            ):
                yield f"data: {json.dumps(item)}\n\n"
            yield "n"
        
        response = StreamingHttpResponse(
            asyncio.run(generate()),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        return response


class ModelLeaderboardView(views.APIView):
    """Model leaderboard view"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        category = request.query_params.get('category', 'overall')
        period = request.query_params.get('period', 'all_time')
        limit = int(request.query_params.get('limit', 10))
        
        # Get latest metrics for each model
        metrics = ModelMetric.objects.filter(
            category=category,
            period=period
        ).select_related('model').order_by(
            'model', '-calculated_at'
        ).distinct('model')
        
        # Sort by ELO rating
        sorted_metrics = sorted(
            metrics,
            key=lambda x: x.elo_rating,
            reverse=True
        )[:limit]
        
        # Prepare response
        leaderboard = []
        for idx, metric in enumerate(sorted_metrics, 1):
            leaderboard.append({
                'rank': idx,
                'model': AIModelSerializer(metric.model).data,
                'metrics': ModelMetricSerializer(metric).data,
                'trend': self._calculate_trend(metric.model, category, period)
            })
        
        return Response({
            'category': category,
            'period': period,
            'leaderboard': leaderboard
        })
    
    def _calculate_trend(self, model, category, period):
        """Calculate ranking trend"""
        # Get previous metric
        previous = ModelMetric.objects.filter(
            model=model,
            category=category,
            period=period
        ).order_by('-calculated_at')[1:2]
        
        if not previous:
            return 'stable'
        
        previous_metric = previous[0]
        current = ModelMetric.objects.filter(
            model=model,
            category=category,
            period=period
        ).order_by('-calculated_at').first()
        
        if current.elo_rating > previous_metric.elo_rating:
            return 'up'
        elif current.elo_rating < previous_metric.elo_rating:
            return 'down'
        return 'stable'


class ModelStatsView(views.APIView):
    """Get model statistics"""
    permission_classes = [AllowAny]
    
    def get(self, request, model_id):
        try:
            model = AIModel.objects.get(id=model_id)
        except AIModel.DoesNotExist:
            return Response(
                {'error': 'Model not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Calculate statistics
        
        stats = {
            'model': AIModelSerializer(model).data,
            'usage': {
                'total_messages': Message.objects.filter(model=model).count(),
                'total_sessions': Message.objects.filter(
                    model=model
                ).values('session').distinct().count(),
                'average_rating': Feedback.objects.filter(
                    message__model=model,
                    rating__isnull=False
                ).aggregate(avg=Avg('rating'))['avg'],
            },
            'performance': self._get_performance_metrics(model),
            'comparisons': self._get_comparison_stats(model),
        }
        
        return Response(stats)
    
    # apps/ai_model/views.py (continued)

    def _get_performance_metrics(self, model):
        """Get performance metrics by category"""
        metrics = ModelMetric.objects.filter(
            model=model,
            period='all_time'
        ).order_by('-calculated_at')
        
        performance = {}
        for metric in metrics:
            if metric.category not in performance:
                performance[metric.category] = {
                    'elo_rating': metric.elo_rating,
                    'win_rate': round(metric.win_rate, 2),
                    'total_comparisons': metric.total_comparisons,
                    'wins': metric.wins,
                    'losses': metric.losses,
                    'ties': metric.ties,
                    'average_rating': float(metric.average_rating) if metric.average_rating else None
                }
        
        return performance
    
    def _get_comparison_stats(self, model):
        """Get comparison statistics against other models"""
        
        # Get all comparisons where this model participated
        comparisons = Feedback.objects.filter(
            feedback_type='preference',
            session__mode='compare'
        ).filter(
            Q(session__model_a=model) | Q(session__model_b=model)
        ).select_related('session__model_a', 'session__model_b', 'preferred_model')
        
        # Calculate win/loss against specific models
        versus_stats = {}
        for feedback in comparisons:
            if feedback.session.model_a == model:
                opponent = feedback.session.model_b
                won = feedback.preferred_model == model
            else:
                opponent = feedback.session.model_a
                won = feedback.preferred_model == model
            
            if opponent.id not in versus_stats:
                versus_stats[opponent.id] = {
                    'opponent': AIModelListSerializer(opponent).data,
                    'wins': 0,
                    'losses': 0,
                    'total': 0
                }
            
            versus_stats[opponent.id]['total'] += 1
            if won:
                versus_stats[opponent.id]['wins'] += 1
            elif feedback.preferred_model == opponent:
                versus_stats[opponent.id]['losses'] += 1
        
        # Calculate win rates
        for stats in versus_stats.values():
            if stats['total'] > 0:
                stats['win_rate'] = round((stats['wins'] / stats['total']) * 100, 2)
            else:
                stats['win_rate'] = 0
        
        return list(versus_stats.values())