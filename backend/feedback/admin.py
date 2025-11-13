from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Avg
from feedback.models import Feedback
from feedback.utils import FeedbackExporter
from django.http import HttpResponse
from ai_model.models import AIModel

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = [
        'feedback_type', 'user_display', 'session_link', 'rating_display',
        'preferred_models_display', 'created_at'
    ]
    list_filter = ['feedback_type', 'rating', 'created_at']
    search_fields = ['user__email', 'user__display_name', 'comment']
    readonly_fields = [
        'id', 'user', 'session_link', 'message_preview',
        'categories_display', 'created_at'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'user', 'session_link', 'feedback_type')
        }),
        ('Feedback Details', {
            'fields': ('rating', 'preferred_model_ids', 'categories_display', 'comment')
        }),
        ('Related Message', {
            'fields': ('message_preview',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        })
    )
    
    def user_display(self, obj):
        if obj.user.is_anonymous:
            return format_html(
                '<span style="color: gray;">Anonymous ({})</span>',
                obj.user.display_name
            )
        return obj.user.display_name
    user_display.short_description = 'User'
    
    def session_link(self, obj):
        url = reverse('admin:chat_session_chatsession_change', args=[obj.session.id])
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.session.title or 'Untitled Session'
        )
    session_link.short_description = 'Session'
    
    def rating_display(self, obj):
        if obj.rating:
            stars = '★' * obj.rating + '☆' * (5 - obj.rating)
            return format_html(
                '<span style="color: gold;">{}</span> ({})',
                stars,
                obj.rating
            )
        return '-'
    rating_display.short_description = 'Rating'
    
    def preferred_models_display(self, obj):
        preferred_ids = obj.preferred_model_ids
        if not preferred_ids:
            return '-'
        
        models = AIModel.objects.filter(id__in=preferred_ids)
        model_names = [model.display_name for model in models]
        
        return ", ".join(model_names)
    preferred_models_display.short_description = 'Preferred Models'

    def categories_display(self, obj):
        if obj.categories:
            return ', '.join(obj.categories)
        return '-'
    categories_display.short_description = 'Categories'
    
    def message_preview(self, obj):
        if obj.message:
            return format_html(
                '<div style="max-width: 500px; word-wrap: break-word;">'
                '<strong>Role:</strong> {}<br>'
                '<strong>Content:</strong> {}...<br>'
                '<a href="{}">View Full Message</a>'
                '</div>',
                obj.message.role,
                obj.message.content[:200],
                reverse('admin:message_message_change', args=[obj.message.id])
            )
        return 'No message associated'
    message_preview.short_description = 'Message Preview'
    
    actions = ['export_feedback', 'analyze_feedback_quality']
    
    def export_feedback(self, request, queryset):
        
        # Export to CSV
        csv_content = FeedbackExporter.export_to_csv(queryset, include_pii=False)
        
        response = HttpResponse(csv_content, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="feedback_export.csv"'
        
        return response
    export_feedback.short_description = 'Export selected feedback to CSV'
    
    def analyze_feedback_quality(self, request, queryset):
        # Analyze feedback quality
        total = queryset.count()
        
        stats = {
            'total': total,
            'with_comments': queryset.exclude(comment='').exclude(comment__isnull=True).count(),
            'with_categories': queryset.exclude(categories=[]).count(),
            'by_type': {},
            'average_rating': None
        }
        
        # By type
        for f_type in ['rating', 'preference', 'report']:
            stats['by_type'][f_type] = queryset.filter(feedback_type=f_type).count()
        
        # Average rating
        ratings = queryset.filter(feedback_type='rating', rating__isnull=False)
        if ratings.exists():
            stats['average_rating'] = ratings.aggregate(avg=Avg('rating'))['avg']
        
        message = f"""
        Feedback Analysis:
        - Total: {stats['total']}
        - With comments: {stats['with_comments']} ({stats['with_comments']/total*100:.1f}%)
        - With categories: {stats['with_categories']} ({stats['with_categories']/total*100:.1f}%)
        - Ratings: {stats['by_type']['rating']}
        - Preferences: {stats['by_type']['preference']}
        - Reports: {stats['by_type']['report']}
        """
        
        if stats['average_rating']:
            message += f"- Average rating: {stats['average_rating']:.2f}"
        
        self.message_user(request, message)
    analyze_feedback_quality.short_description = 'Analyze selected feedback quality'