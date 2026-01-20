from django.db import models
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
        """Increment the usage count for this prompt."""
        self.usage_count += 1
        self.save(update_fields=['usage_count', 'updated_at'])
