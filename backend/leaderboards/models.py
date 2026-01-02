from django.db import models

# Create your models here.
class Leaderboard(models.Model):
    # --- Choices Definitions ---
    ARENA_TYPE_CHOICES = [
        ('llm', 'LLM'),
        ('asr', 'ASR'),
        ('tts', 'TTS'),
        ('ocr', 'OCR'),
    ]

    ORGANIZATION_CHOICES = [
        ('ai4bharat', 'AI4Bharat'),
        ('aquarium', 'Aquarium'),
        ('ai4x', 'AI4X'),
    ]

    LANGUAGE_CHOICES = [
        ("English", "English"),
        ("Assamese", "Assamese"),
        ("Bengali", "Bengali"),
        ("Burmese", "Burmese"),
        ("Bodo", "Bodo"),
        ("Dogri", "Dogri"),
        ("Gujarati", "Gujarati"),
        ("Hindi", "Hindi"),
        ("Kannada", "Kannada"),
        ("Kashmiri", "Kashmiri"),
        ("Konkani", "Konkani"),
        ("Maithili", "Maithili"),
        ("Malayalam", "Malayalam"),
        ("Manipuri", "Manipuri"),
        ("Marathi", "Marathi"),
        ("Nepali", "Nepali"),
        ("Odia", "Odia"),
        ("Punjabi", "Punjabi"),
        ("Sanskrit", "Sanskrit"),
        ("Santali", "Santali"),
        ("Sindhi", "Sindhi"),
        ("Sinhala", "Sinhala"),
        ("Tamil", "Tamil"),
        ("Telugu", "Telugu"),
        ("Thai", "Thai"),
        ("Urdu", "Urdu"),
    ]

    # --- Database Fields ---
    
    # Stores the actual rows of the leaderboard (Rank, Model, Score, CI, etc.)
    leaderboard_json = models.JSONField(
        help_text="List of objects containing: rank, model, score, votes, organization, license, ci"
    )

    arena_type = models.CharField(
        max_length=10, 
        choices=ARENA_TYPE_CHOICES,
        default='llm'
    )
    
    # The organization hosting/running this specific benchmark
    organization = models.CharField(
        max_length=50, 
        choices=ORGANIZATION_CHOICES,
        default='ai4bharat'
    )
    
    language = models.CharField(
        max_length=50, 
        choices=LANGUAGE_CHOICES,
        default='English'
    )
    
    benchmark_name = models.CharField(
        max_length=255,
        help_text="Name of the specific benchmark (e.g., 'IndicMMLU-v1')"
    )

    # Standard timestamps for record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Optional: Ensure we don't duplicate a benchmark for the same language/org/type
        unique_together = ('benchmark_name', 'language', 'arena_type', 'organization')
        verbose_name = "Leaderboard"
        verbose_name_plural = "Leaderboards"

    def __str__(self):
        return f"{self.benchmark_name} ({self.language}) - {self.get_arena_type_display()}"