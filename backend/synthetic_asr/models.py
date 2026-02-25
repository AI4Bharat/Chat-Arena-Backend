from django.db import models
from django.conf import settings


class Job(models.Model):
    # Status choices for pipeline tracking
    STATUS_CHOICES = [
        ('SUBMITTED', 'Submitted'),
        ('SENTENCE_GENERATED', 'Sentences Generated'),
        ('AUDIO_GENERATED', 'Audio Generated'),
        ('AUDIO_VERIFIED', 'Audio Verified'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    # Original fields - DO NOT MODIFY
    job_id = models.CharField(max_length=128, unique=True)
    payload = models.JSONField()
    status = models.CharField(max_length=64, default='SUBMITTED', choices=STATUS_CHOICES)
    result = models.JSONField(null=True, blank=True)
    error = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # New fields for pipeline tracking - DO NOT BREAK EXISTING CODE
    progress_percentage = models.IntegerField(default=0, help_text="Progress percentage 0-100")
    current_step = models.CharField(max_length=100, blank=True, help_text="Current pipeline step")
    step_details = models.JSONField(default=dict, blank=True, help_text="Details about current step")
    total_steps = models.IntegerField(default=6, help_text="Total steps in pipeline")
    
    # Track timestamps for each step
    sentence_generation_started_at = models.DateTimeField(null=True, blank=True)
    sentence_generation_completed_at = models.DateTimeField(null=True, blank=True)
    audio_generation_started_at = models.DateTimeField(null=True, blank=True)
    audio_generation_completed_at = models.DateTimeField(null=True, blank=True)
    audio_verification_started_at = models.DateTimeField(null=True, blank=True)
    audio_verification_completed_at = models.DateTimeField(null=True, blank=True)
    
    # File paths for artifacts
    sentences_file_path = models.CharField(max_length=500, blank=True)
    audio_manifest_path = models.CharField(max_length=500, blank=True)
    dataset_manifest_path = models.CharField(max_length=500, blank=True)
    
    # Generation attempt counter (for retries)
    generation_attempts = models.IntegerField(default=0)

    # Owner (who created the job) for privacy scoping
    # Nullable for backward compatibility with existing rows
    created_by = models.ForeignKey(
        'user.User',  # reference to our custom user model
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='synthetic_asr_jobs',
        db_index=True,
        help_text="User who created this job"
    )

    class Meta:
        db_table = 'synthetic_asr_jobs'

    def __str__(self):
        return f"{self.job_id} - {self.status}"
    
    def update_progress(self, percentage, step, details=None):
        """Update job progress - helper method"""
        self.progress_percentage = percentage
        self.current_step = step
        if details:
            self.step_details = details
        self.save(update_fields=['progress_percentage', 'current_step', 'step_details', 'updated_at'])
