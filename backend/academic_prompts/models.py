from django.db import models
from django.db.models import F
import uuid
from ai_model.models import AIModel


class AcademicPrompt(models.Model):
    """
    Model to store academic benchmarking prompts for TTS Arena.
    Prompts are uniformly sampled based on usage count to ensure even distribution.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text = models.TextField(help_text="The prompt text")
    language = models.CharField(
        max_length=10,
        help_text="Language code (e.g., 'en', 'hi', 'mr')"
    )
    model_a = models.ForeignKey(AIModel, on_delete=models.CASCADE, related_name='academic_prompts_model_a', null=True, blank=True)
    model_b = models.ForeignKey(AIModel, on_delete=models.CASCADE, related_name='academic_prompts_model_b', null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True, help_text="Gender for voice selection")
    voice_a = models.CharField(max_length=100, null=True, blank=True, help_text="Specific voice/speaker for model_a. If null, randomly selected based on gender.")
    voice_b = models.CharField(max_length=100, null=True, blank=True, help_text="Specific voice/speaker for model_b. If null, randomly selected based on gender.")
    usage_count = models.IntegerField(
        default=0,
        help_text="Number of times this prompt has been used"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this prompt is active and can be used"
    )
    normalized = models.BooleanField(null=True, blank=True, help_text="Whether this prompt has been normalized")
    domain = models.CharField(max_length=100, null=True, blank=True, help_text="Domain or category of the prompt")

    class Meta:
        db_table = 'academic_prompts'
        indexes = [
            models.Index(fields=['language', 'is_active']),
            models.Index(fields=['usage_count']),
        ]
        ordering = ['usage_count', 'created_at']

    def __str__(self):
        return f"{self.language}: {self.text[:50]}..."

    def increment_usage(self):
        """Increment the usage count for this prompt atomically."""
        AcademicPrompt.objects.filter(pk=self.pk).update(usage_count=F('usage_count') + 1)
        self.refresh_from_db(fields=['usage_count'])
