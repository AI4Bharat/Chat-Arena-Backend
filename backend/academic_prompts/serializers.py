from rest_framework import serializers
from .models import AcademicPrompt


class AcademicPromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicPrompt
        fields = ['id', 'text', 'language', 'usage_count', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'usage_count', 'created_at', 'updated_at']
