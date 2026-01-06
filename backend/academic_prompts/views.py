from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Min
from .models import AcademicPrompt
from .serializers import AcademicPromptSerializer
import random


class AcademicPromptViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing academic prompts.
    Provides CRUD operations and a special endpoint to get a random prompt.
    """
    queryset = AcademicPrompt.objects.all()
    serializer_class = AcademicPromptSerializer
    permission_classes = []  # Allow public access for reading prompts

    @action(detail=False, methods=['get'], url_path='random')
    def get_random_prompt(self, request):
        """
        Get a random prompt for the specified language.
        Prioritizes prompts with lower usage counts to ensure uniform distribution.

        Query params:
            language: Language code (e.g., 'en', 'hi', 'mr')
        """
        language = request.query_params.get('language', 'en')

        # Get all active prompts for the language
        prompts = AcademicPrompt.objects.filter(
            language=language,
            is_active=True
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

        # Increment usage count
        selected_prompt.increment_usage()

        # Serialize and return
        serializer = self.get_serializer(selected_prompt)
        return Response(serializer.data)
