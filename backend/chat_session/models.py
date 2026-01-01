from django.db import models
import uuid
import secrets
from ai_model.models import AIModel
from user.models import User


class ChatSession(models.Model):
    MODE_CHOICES = [
        ('direct', 'Direct Chat'),
        ('compare', 'Compare Models'),
        ('random', 'Random Models')
    ]

    TYPE_CHOICES = [
        ('LLM', 'Large Language Model'),
        ('ASR', 'Automatic Speech Recognition'),
        ('TTS', 'Text to Speech'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_sessions')
    mode = models.CharField(max_length=50, choices=MODE_CHOICES)
    title = models.CharField(max_length=255, blank=True)
    model_a = models.ForeignKey(
        AIModel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='sessions_as_model_a'
    )
    model_b = models.ForeignKey(
        AIModel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='sessions_as_model_b'
    )
    is_public = models.BooleanField(default=False)
    share_token = models.CharField(max_length=100, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # For anonymous user cleanup
    meta_stats_json = models.JSONField(default=dict, blank=True)
    session_type = models.CharField(max_length=100, default='LLM', choices=TYPE_CHOICES)  # e.g., 'llm', 'asr', 'tts
    is_pinned = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'chat_sessions'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['share_token']),
            models.Index(fields=['mode']),
            models.Index(fields=['expires_at']),
        ]
        ordering = ['-updated_at']
    
    def save(self, *args, **kwargs):
        # Generate title if not provided
        # if not self.title and self.pk:
        #     first_message = self.messages.filter(role='user').first()
        #     if first_message:
        #         self.title = first_message.content[:50] + "..." if len(first_message.content) > 50 else first_message.content
        
        # Set expiration for anonymous users
        if self.user.is_anonymous and not self.expires_at:
            self.expires_at = self.user.anonymous_expires_at
            
        super().save(*args, **kwargs)
    
    def generate_share_token(self):
        """Generate a unique share token"""
        self.share_token = secrets.token_urlsafe(16)
        self.save()
        return self.share_token
    
    def __str__(self):
        return f"{self.mode} - {self.title or 'Untitled'} ({self.user.display_name})"
    
    @property
    def has_feedback(self):
        """
        Checks if any feedback has been submitted for this session.
        """
        return self.feedbacks.exists()