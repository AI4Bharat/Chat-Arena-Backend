from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
from ai_model.models import AIModel
from chat_session.models import ChatSession
from message.models import Message
from user.models import User
from django.contrib.postgres.fields import ArrayField

class Feedback(models.Model):
    FEEDBACK_TYPE_CHOICES = [
        ('preference', 'Preference'),
        ('rating', 'Rating'),
        ('report', 'Report Issue')
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedbacks')
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='feedbacks')
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='feedbacks', null=True, blank=True)
    feedback_type = models.CharField(max_length=50, choices=FEEDBACK_TYPE_CHOICES)
    preferred_model_ids = ArrayField(
        models.UUIDField(),
        blank=True,
        default=list,
        help_text="List of AI Model IDs"
    )
    rating = models.IntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    categories = models.JSONField(
        default=list,
        blank=True,
        help_text="Categories like accuracy, helpfulness, creativity, etc."
    )
    comment = models.TextField(blank=True)
    additional_feedback_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional structured feedback data (e.g., TTS evaluation parameters)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'feedback'
        indexes = [
            models.Index(fields=['session', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['feedback_type']),
        ]
        ordering = ['-created_at']
        unique_together = [
            ['user', 'session', 'message', 'feedback_type']
        ]
    
    def __str__(self):
        return f"{self.feedback_type} by {self.user.display_name}"
