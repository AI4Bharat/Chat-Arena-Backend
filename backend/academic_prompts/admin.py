from django.contrib import admin
from .models import AcademicPrompt


@admin.register(AcademicPrompt)
class AcademicPromptAdmin(admin.ModelAdmin):
    list_display = ['id', 'language', 'text_preview', 'usage_count', 'is_active', 'created_at']
    list_filter = ['language', 'is_active', 'created_at']
    search_fields = ['text', 'language']
    readonly_fields = ['id', 'created_at', 'updated_at', 'usage_count']
    ordering = ['usage_count', 'language', 'created_at']

    def text_preview(self, obj):
        return obj.text[:100] + '...' if len(obj.text) > 100 else obj.text
    text_preview.short_description = 'Text'
