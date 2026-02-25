from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Min, Q, Sum, Count
from .models import AcademicPrompt
from .serializers import AcademicPromptSerializer, AcademicPromptBulkCreateSerializer
import random


class AcademicPromptViewSet(viewsets.ModelViewSet):
    queryset = AcademicPrompt.objects.select_related('model_a', 'model_b').all()
    serializer_class = AcademicPromptSerializer
    permission_classes = []

    def get_queryset(self):
        """Apply filters from query parameters."""
        queryset = AcademicPrompt.objects.select_related('model_a', 'model_b').all()

        language = self.request.query_params.get('language')
        if language:
            queryset = queryset.filter(language=language)

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        model_code = self.request.query_params.get('model_code')
        if model_code:
            queryset = queryset.filter(
                Q(model_a__model_code=model_code) | Q(model_b__model_code=model_code)
            )

        model_a_code = self.request.query_params.get('model_a_code')
        if model_a_code:
            queryset = queryset.filter(model_a__model_code=model_a_code)

        model_b_code = self.request.query_params.get('model_b_code')
        if model_b_code:
            queryset = queryset.filter(model_b__model_code=model_b_code)

        has_models = self.request.query_params.get('has_models')
        if has_models is not None:
            if has_models.lower() == 'true':
                queryset = queryset.filter(model_a__isnull=False, model_b__isnull=False)
            else:
                queryset = queryset.filter(Q(model_a__isnull=True) | Q(model_b__isnull=True))

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(text__icontains=search)

        return queryset

    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        """
        Bulk create academic prompts.
        """
        serializer = AcademicPromptBulkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created_prompts = serializer.save()

        return Response({
            'message': f'Successfully created {len(created_prompts)} prompts',
            'created_count': len(created_prompts),
            'prompts': AcademicPromptSerializer(created_prompts, many=True).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='random')
    def get_random_prompt(self, request):
        """
        Get a random prompt for the specified language.
        Prioritizes prompts with lower usage counts to ensure uniform distribution.

        Query params:
            language: Language code (e.g., 'en', 'hi', 'mr')
        """
        language = request.query_params.get('language', 'en')

        prompts = AcademicPrompt.objects.filter(
            language=language,
            is_active=True,
            model_a__isnull=False,
            model_b__isnull=False
        )

        if not prompts.exists():
            return Response(
                {'error': f'No active prompts found for language: {language}'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get the minimum usage count
        min_usage_count = prompts.aggregate(Min('usage_count'))['usage_count__min']

        # Get all prompts with minimum usage count (for uniform distribution)
        least_used_prompts = prompts.filter(usage_count=min_usage_count)

        # Randomly select one from the least used prompts
        selected_prompt = random.choice(list(least_used_prompts))

        # Serialize and return
        serializer = self.get_serializer(selected_prompt)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='languages')
    def get_languages(self, request):
        """
        Get list of available languages with prompt counts.
        """
        languages = AcademicPrompt.objects.filter(is_active=True).values('language').distinct()
        language_stats = []

        for lang in languages:
            count = AcademicPrompt.objects.filter(
                language=lang['language'],
                is_active=True
            ).count()
            with_models_count = AcademicPrompt.objects.filter(
                language=lang['language'],
                is_active=True,
                model_a__isnull=False,
                model_b__isnull=False
            ).count()
            language_stats.append({
                'language': lang['language'],
                'total_prompts': count,
                'prompts_with_models': with_models_count
            })

        return Response(language_stats)

    @action(detail=False, methods=['get'], url_path='stats')
    def get_stats(self, request):
        """
        Get usage statistics for academic prompts.
        """
        total_prompts = AcademicPrompt.objects.count()
        active_prompts = AcademicPrompt.objects.filter(is_active=True).count()
        prompts_with_models = AcademicPrompt.objects.filter(
            model_a__isnull=False,
            model_b__isnull=False
        ).count()
        total_usage = AcademicPrompt.objects.aggregate(
            total=Sum('usage_count')
        )['total'] or 0

        usage_distribution = AcademicPrompt.objects.values('usage_count').annotate(
            count=Count('id')
        ).order_by('usage_count')[:10]

        return Response({
            'total_prompts': total_prompts,
            'active_prompts': active_prompts,
            'prompts_with_models': prompts_with_models,
            'total_usage': total_usage,
            'usage_distribution': list(usage_distribution)
        })

    @action(detail=False, methods=['post'], url_path='reset-usage')
    def reset_usage(self, request):
        """
        Reset usage count for all prompts or specific language.
        """
        language = request.query_params.get('language')

        queryset = AcademicPrompt.objects.all()
        if language:
            queryset = queryset.filter(language=language)

        updated_count = queryset.update(usage_count=0)

        return Response({
            'message': f'Reset usage count for {updated_count} prompts',
            'updated_count': updated_count
        })
