from django.contrib import admin
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from message.utlis import MessageAnalyzer
from message.models import Message, MessageRelation


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = [
        'truncated_content', 'role', 'session_link', 'model_display',
        'status', 'position', 'created_at'
    ]
    list_filter = ['role', 'status', 'created_at']
    search_fields = ['content', 'session__title']
    readonly_fields = [
        'id', 'formatted_content', 'parent_links', 'child_links',
        'message_metadata', 'created_at'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'session', 'role', 'formatted_content')
        }),
        ('Model Information', {
            'fields': ('model', 'participant', 'status', 'failure_reason')
        }),
        ('Relationships', {
            'fields': ('parent_links', 'child_links', 'position')
        }),
        ('Additional Data', {
            'fields': ('attachments', 'message_metadata'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        })
    )
    
    def truncated_content(self, obj):
        max_length = 100
        if hasattr(obj, 'content'):
            content = obj.content
            if len(content) > max_length:
                return f"{content[:max_length]}..."
            return content
        return str(obj)
    truncated_content.short_description = 'Content'
    
    def session_link(self, obj):
        return format_html(
            '<a href="/admin/chat_session/chatsession/{}/change/">{}</a>',
            obj.session.id,
            obj.session.title or 'Untitled'
        )
    session_link.short_description = 'Session'
    
    def model_display(self, obj):
        if obj.model:
            return f"{obj.model.display_name} ({obj.model.provider})"
        return '-'
    model_display.short_description = 'Model'
    
    def formatted_content(self, obj):
        """Display formatted content with syntax highlighting"""
        
        content = escape(obj.content)
        
        # Highlight code blocks
        code_blocks = MessageAnalyzer.extract_code_blocks(obj.content)
        if code_blocks:
            for block in code_blocks:
                # Simple syntax highlighting placeholder
                highlighted = f'<pre style="background: #f4f4f4; padding: 10px; border-radius: 5px;"><code>{escape(block["code"])}</code></pre>'
                content = content.replace(f'```{block["language"]}\n{block["code"]}```', highlighted)
        
        # Convert line breaks
        content = content.replace('\n', '<br>')
        
        return mark_safe(f'<div style="max-width: 800px; word-wrap: break-word;">{content}</div>')
    formatted_content.short_description = 'Content'
    
    def parent_links(self, obj):
        if not obj.parent_message_ids:
            return '-'
        
        links = []
        for parent_id in obj.parent_message_ids:
            try:
                parent = Message.objects.get(id=parent_id)
                parent_preview = self.truncated_content(parent)[:50]
                links.append(format_html(
                    '<a href="/admin/message/message/{}/change/">Parent: {} ({})</a>',
                    parent_id,
                    parent_preview,
                    parent.role
                ))
            except Message.DoesNotExist:
                links.append(f'Parent: {parent_id} (deleted)')
        
        return mark_safe('<br>'.join(links))
    parent_links.short_description = 'Parent Messages'
    
    def child_links(self, obj):
        if not obj.child_ids:
            return '-'
        
        links = []
        for child_id in obj.child_ids:
            try:
                child = Message.objects.get(id=child_id)
                child_preview = self.truncated_content(child)[:50]
                links.append(format_html(
                    '<a href="/admin/message/message/{}/change/">Child: {} ({})</a>',
                    child_id,
                    child_preview,
                    child.role
                ))
            except Message.DoesNotExist:
                links.append(f'Child: {child_id} (deleted)')
        
        return mark_safe('<br>'.join(links))
    child_links.short_description = 'Child Messages'
    
    def message_metadata(self, obj):
        """Display metadata in a formatted way"""
        if not obj.metadata:
            return '-'
        
        html = ['<table style="width: 100%;">']
        for key, value in obj.metadata.items():
            html.append(f'<tr><td><strong>{key}:</strong></td><td>{value}</td></tr>')
        html.append('</table>')
        
        return mark_safe(''.join(html))
    message_metadata.short_description = 'Metadata'
    
    actions = ['mark_as_success', 'mark_as_failed', 'analyze_messages']
    
    def mark_as_success(self, request, queryset):
        updated = queryset.update(status='success', failure_reason=None)
        self.message_user(request, f'{updated} messages marked as success.')
    mark_as_success.short_description = 'Mark selected messages as success'
    
    def mark_as_failed(self, request, queryset):
        updated = queryset.update(status='failed')
        self.message_user(request, f'{updated} messages marked as failed.')
    mark_as_failed.short_description = 'Mark selected messages as failed'
    
    def analyze_messages(self, request, queryset):
        
        analysis = MessageAnalyzer.analyze_conversation_quality(list(queryset))
        
        summary = [
            f"Total messages: {analysis['total_messages']}",
            f"Average length: {analysis['avg_message_length']:.0f} chars",
            f"Questions: {analysis['question_count']}",
            f"Code blocks: {analysis['code_blocks_count']}",
            f"Languages: {', '.join(analysis['language_diversity'])}",
        ]
        
        self.message_user(
            request,
            mark_safe('<br>'.join(summary)),
            level='INFO'
        )
    analyze_messages.short_description = 'Analyze selected messages'
    
@admin.register(MessageRelation)
class MessageRelationAdmin(admin.ModelAdmin):
    list_display = ['parent_preview', 'child_preview', 'relation_type', 'created_at']
    list_filter = ['relation_type', 'created_at']
    readonly_fields = ['parent', 'child', 'relation_type', 'created_at']
    
    def parent_preview(self, obj):
        return format_html(
            '<a href="/admin/message/message/{}/change/">{}</a>',
            obj.parent.id,
            obj.parent.content[:50] + '...'
        )
    parent_preview.short_description = 'Parent Message'
    
    def child_preview(self, obj):
        return format_html(
            '<a href="/admin/message/message/{}/change/">{}</a>',
            obj.child.id,
            obj.child.content[:50] + '...'
        )
    child_preview.short_description = 'Child Message'
    
    def has_add_permission(self, request):
        # Relations are created automatically
        return False