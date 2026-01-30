from rest_framework import serializers
from .models import AcademicPrompt
from ai_model.models import AIModel


class AcademicPromptSerializer(serializers.ModelSerializer):
    """Serializer for AcademicPrompt with model references."""
    model_a_code = serializers.SlugRelatedField(source='model_a', slug_field='model_code', queryset=AIModel.objects.all(), required=False, allow_null=True)
    model_b_code = serializers.SlugRelatedField(source='model_b', slug_field='model_code', queryset=AIModel.objects.all(), required=False, allow_null=True)
    model_a_display = serializers.CharField(source='model_a.display_name', read_only=True)
    model_b_display = serializers.CharField(source='model_b.display_name', read_only=True)

    class Meta:
        model = AcademicPrompt
        fields = [
            'id', 'text', 'language',
            'model_a', 'model_b',
            'model_a_code', 'model_b_code',
            'model_a_display', 'model_b_display',
            'gender', 'voice_a', 'voice_b',
            'usage_count', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'usage_count', 'created_at', 'updated_at', 'model_a_display', 'model_b_display']


class AcademicPromptBulkCreateSerializer(serializers.Serializer):
    """Serializer for bulk creating academic prompts."""
    prompts = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        max_length=10000,
        help_text="List of prompts to create"
    )

    def validate_prompts(self, value):
        """Validate each prompt in the list."""
        validated_prompts = []
        errors = []

        for i, prompt_data in enumerate(value):
            if 'text' not in prompt_data:
                errors.append(f"Prompt {i}: 'text' is required")
                continue
            if 'language' not in prompt_data:
                errors.append(f"Prompt {i}: 'language' is required")
                continue

            validated_prompt = {
                'text': prompt_data['text'],
                'language': prompt_data['language'],
                'is_active': prompt_data.get('is_active', True),
                'gender': prompt_data.get('gender'),
                'voice_a': prompt_data.get('voice_a'),
                'voice_b': prompt_data.get('voice_b'),
            }

            if 'model_a_code' in prompt_data and prompt_data['model_a_code']:
                try:
                    model_a = AIModel.objects.get(model_code=prompt_data['model_a_code'])
                    validated_prompt['model_a'] = model_a
                except AIModel.DoesNotExist:
                    errors.append(f"Prompt {i}: model_a_code '{prompt_data['model_a_code']}' not found")
                    continue

            if 'model_b_code' in prompt_data and prompt_data['model_b_code']:
                try:
                    model_b = AIModel.objects.get(model_code=prompt_data['model_b_code'])
                    validated_prompt['model_b'] = model_b
                except AIModel.DoesNotExist:
                    errors.append(f"Prompt {i}: model_b_code '{prompt_data['model_b_code']}' not found")
                    continue

            validated_prompts.append(validated_prompt)

        if errors:
            raise serializers.ValidationError(errors)

        return validated_prompts

    def create(self, validated_data):
        """Bulk create prompts."""
        prompts_data = validated_data['prompts']
        created_prompts = []

        for prompt_data in prompts_data:
            prompt = AcademicPrompt.objects.create(**prompt_data)
            created_prompts.append(prompt)

        return created_prompts
