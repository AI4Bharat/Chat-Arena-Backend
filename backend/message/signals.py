from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from message.utlis import MessageCache
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from message.models import Message
from message.serializers import MessageSerializer


@receiver(post_save, sender=Message)
def message_saved(sender, instance, created, **kwargs):
    """Send WebSocket notification when message is saved"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            # Invalidate caches even if no socket layer
            MessageCache.invalidate_message_cache(str(instance.id))
            return
        
        # Send to session group
        group_name = f"session_{instance.session_id}"
        
        event_type = 'message_created' if created else 'message_updated'
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'message_update',
                'message': MessageSerializer(instance).data,
                'action': event_type
            }
        )
    except Exception as e:
        print(f"Warning: Signal failed to send socket update: {e}")
    
    # Invalidate caches
    MessageCache.invalidate_message_cache(str(instance.id))


@receiver(post_delete, sender=Message)
def message_deleted(sender, instance, **kwargs):
    """Send WebSocket notification when message is deleted"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
            
        # Send to session group
        group_name = f"session_{instance.session_id}"
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'message_update',
                'message_id': str(instance.id),
                'action': 'message_deleted'
            }
        )
    except Exception as e:
        print(f"Warning: Signal failed to send delete socket update: {e}")