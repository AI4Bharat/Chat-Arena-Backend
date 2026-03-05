from django.db import models
import uuid

class AIModel(models.Model):
    PROVIDER_CHOICES = [
        ('openai', 'OpenAI'),
        ('google', 'Google'),
        ('anthropic', 'Anthropic'),
        ('meta', 'Meta'),
        ('grok', 'Grok'),
        ('mistral', 'Mistral'),
        ('deepseek', 'DeepSeek'),
        ('qwen', 'Qwen'),
        ('sarvam', 'Sarvam'),
        ('ibm', 'IBM'),
        ('ai4b', 'AI4Bharat'),
        ('elevenlabs', 'ElevenLabs'),
        ('minimax', 'MiniMax'),
        ('cartesia', 'Cartesia'),
        ('murf', 'MurfAI'),
    ]

    TYPE_CHOICES = [
        ('LLM', 'Large Language Model'),
        ('ASR', 'Automatic Speech Recognition'),
        ('TTS', 'Text to Speech'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=100, choices=PROVIDER_CHOICES)
    model_name = models.CharField(max_length=255)
    model_code = models.CharField(max_length=100, unique=True)  # e.g., 'gpt-4', 'claude-3'
    model_type = models.CharField(max_length=100, default='LLM', choices=TYPE_CHOICES)  # e.g., 'llm', 'asr', 'tts
    display_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    capabilities = models.JSONField(default=list, blank=True)  # ['text', 'code', 'image', etc.]
    supported_languages = models.JSONField(default=list, blank=True) # For ASR/TTS models
    max_tokens = models.IntegerField(null=True, blank=True)
    supports_streaming = models.BooleanField(default=True)
    is_thinking_model = models.BooleanField(default=False)
    is_fresh_model = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    release_date = models.DateField(default="2020-01-01")
    config = models.JSONField(default=dict, blank=True)  # API endpoints, model-specific settings
    created_at = models.DateTimeField(auto_now_add=True)
    meta_stats_json = models.JSONField(default=dict, blank=True)
    url = models.URLField(max_length=500, blank=True, null=True)
    
    class Meta:
        db_table = 'ai_models'
        indexes = [
            models.Index(fields=['provider', 'is_active']),
            models.Index(fields=['model_code']),
        ]
        ordering = ['-release_date', 'provider', 'display_name']
    
    def __str__(self):
        return f"{self.display_name} ({self.provider})"
