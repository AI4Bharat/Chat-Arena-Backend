from django.db import models
from django.utils import timezone
import uuid
from datetime import timedelta

class User(models.Model):
    AUTH_PROVIDER_CHOICES = [
        ('google', 'Google'),
        ('anonymous', 'Anonymous')
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, null=True, blank=True)
    display_name = models.CharField(max_length=255)
    auth_provider = models.CharField(max_length=50, choices=AUTH_PROVIDER_CHOICES)
    firebase_uid = models.CharField(max_length=255, unique=True, null=True, blank=True)
    is_anonymous = models.BooleanField(default=False)
    anonymous_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    preferences = models.JSONField(default=dict, blank=True)
    meta_stats_json = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['firebase_uid']),
            models.Index(fields=['is_anonymous', 'anonymous_expires_at']),
        ]
        
    def save(self, *args, **kwargs):
        # Set expiration for anonymous users (30 days)
        if self.is_anonymous and not self.anonymous_expires_at:
            self.anonymous_expires_at = timezone.now() + timedelta(days=30)
        # Set display name if not provided
        if not self.display_name:
            if self.email:
                self.display_name = self.email.split('@')[0]
            else:
                self.display_name = f"Anonymous_{str(self.id)[:8]}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.display_name} ({self.auth_provider})"
    
    @property
    def is_authenticated(self):
        """
        This is required for Django REST Framework's IsAuthenticated permission
        """
        return True
