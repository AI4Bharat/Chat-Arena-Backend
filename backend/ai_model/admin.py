from django.contrib import admin
from django.utils.html import format_html
from ai_model.models import AIModel
from message.models import Message


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = [
        'display_name', 'provider', 'model_code', 'model_type',
        'is_active', 'supports_streaming', 'is_thinking_model', 'is_fresh_model', 'capabilities_display',
        'created_at'
    ]
    list_filter = ['provider', 'model_type', 'is_active', 'supports_streaming', 'is_thinking_model', 'is_fresh_model', 'created_at']
    search_fields = ['display_name', 'model_name', 'model_code', 'description']
    readonly_fields = ['id', 'created_at', 'usage_stats']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'provider', 'model_name', 'model_code', 'display_name', 'model_type')
        }),
        ('Description', {
            'fields': ('description',)
        }),
        ('Configuration', {
            'fields': ('capabilities', 'supported_languages', 'max_tokens', 'supports_streaming', 'is_thinking_model', 'is_fresh_model', 'config')
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'release_date')
        }),
        ('Statistics', {
            'fields': ('usage_stats',),
            'classes': ('collapse',)
        })
    )
    
    def capabilities_display(self, obj):
        """Display capabilities as badges"""
        if not obj.capabilities:
            return '-'
        
        colors = {
            'text': 'blue',
            'code': 'green',
            'vision': 'purple',
            'creative': 'orange',
            'reasoning': 'red'
        }
        
        badges = []
        for cap in obj.capabilities:
            color = colors.get(cap, 'gray')
            badges.append(
                f'<span style="background-color: {color}; color: white; '
                f'padding: 2px 6px; border-radius: 3px; margin-right: 4px;">'
                f'{cap}</span>'
            )
        
        return format_html(''.join(badges))
    
    capabilities_display.short_description = 'Capabilities'
    
    def usage_stats(self, obj):
        """Display usage statistics"""
        
        total_messages = Message.objects.filter(model=obj).count()
        latest_metric = obj.metrics.filter(
            category='overall',
            period='all_time'
        ).order_by('-calculated_at').first()
        
        stats = [
            f"<strong>Total Messages:</strong> {total_messages}",
        ]
        
        if latest_metric:
            stats.extend([
                f"<strong>ELO Rating:</strong> {latest_metric.elo_rating}",
                f"<strong>Win Rate:</strong> {latest_metric.win_rate:.1f}%",
                f"<strong>Total Comparisons:</strong> {latest_metric.total_comparisons}"
            ])
        
        return format_html('<br>'.join(stats))
    
    usage_stats.short_description = 'Usage Statistics'
    
    actions = ['activate_models', 'deactivate_models', 'test_model_connection']
    
    def activate_models(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} models activated.')
    
    activate_models.short_description = 'Activate selected models'
    
    def deactivate_models(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} models deactivated.')
    
    deactivate_models.short_description = 'Deactivate selected models'
    
    def test_model_connection(self, request, queryset):
        from .services import AIModelService
        import asyncio
        
        service = AIModelService()
        results = []
        
        for model in queryset:
            try:
                validation = service.validate_model_configuration(model)
                if validation['is_valid']:
                    results.append(f"✓ {model.display_name}: Valid")
                else:
                    results.append(f"✗ {model.display_name}: Invalid")
            except Exception as e:
                results.append(f"✗ {model.display_name}: Error - {str(e)}")
        
        self.message_user(
            request, 
            format_html('<br>'.join(results)),
            level='INFO'
        )
    
    test_model_connection.short_description = 'Test model connection'
