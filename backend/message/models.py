from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.fields import ArrayField
import uuid
from ai_model.models import AIModel
from chat_session.models import ChatSession

class Message(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System')
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('streaming', 'Streaming'),
        ('success', 'Success'),
        ('failed', 'Failed')
    ]
    
    PARTICIPANT_CHOICES = [
        ('a', 'Model A'),
        ('b', 'Model B')
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=50, choices=ROLE_CHOICES)
    content = models.TextField()
    model = models.ForeignKey(AIModel, on_delete=models.SET_NULL, null=True, blank=True)
    parent_message_ids = ArrayField(
        models.UUIDField(),
        default=list,
        blank=True,
        help_text="Array of parent message IDs for branching conversations"
    )
    child_ids = ArrayField(
        models.UUIDField(),
        default=list,
        blank=True,
        help_text="Array of child message IDs for easy traversal"
    )
    position = models.IntegerField()
    participant = models.CharField(
        max_length=10, 
        choices=PARTICIPANT_CHOICES, 
        null=True, 
        blank=True,
        help_text="Participant identifier for compare mode"
    )
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    failure_reason = models.TextField(null=True, blank=True)
    attachments = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Store tokens used, latency, model parameters, etc."
    )
    feedback = models.CharField(
        max_length=20,
        null=True,
        default=None,
        help_text="User feedback: Tie for both models, Model A and Model B for respective models and Both are bad for neither"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    meta_stats_json = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'messages'
        ordering = ['session', 'position']
        indexes = [
            models.Index(fields=['session', 'position']),
            GinIndex(fields=['parent_message_ids']),
            GinIndex(fields=['child_ids']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-increment position if not set
        if self.position is None:
            last_message = Message.objects.filter(session=self.session).order_by('-position').first()
            self.position = (last_message.position + 1) if last_message else 0
        
        # Validate participant field based on session mode
        if self.session.mode == 'compare' and self.role == 'assistant':
            if self.participant not in ['a', 'b']:
                raise ValueError("Participant must be 'a' or 'b' in compare mode")
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class MessageRelation(models.Model):
    """Optional table for complex message relationship queries"""
    RELATION_TYPE_CHOICES = [
        ('reply', 'Reply'),
        ('branch', 'Branch'),
        ('merge', 'Merge')
    ]
    
    parent = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='parent_relations')
    child = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='child_relations')
    relation_type = models.CharField(max_length=50, choices=RELATION_TYPE_CHOICES, default='reply')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'message_relations'
        unique_together = ['parent', 'child']
        indexes = [
            models.Index(fields=['parent', 'child']),
        ]
