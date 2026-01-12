from rest_framework import serializers
from django.db import transaction
from message.models import Message, MessageRelation
from ai_model.serializers import AIModelListSerializer
from ai_model.models import AIModel
import uuid
from django.db.models import F

class MessageSerializer(serializers.ModelSerializer):
    """Full message serializer"""
    model = AIModelListSerializer(read_only=True)
    children_count = serializers.SerializerMethodField()
    has_feedback = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id', 'session', 'role', 'content', 'model',
            'parent_message_ids', 'child_ids', 'position',
            'participant', 'status', 'failure_reason',
            'attachments', 'metadata', 'created_at',
            'children_count', 'has_feedback'
        ]
        read_only_fields = ['id', 'child_ids', 'created_at']
    
    def get_children_count(self, obj):
        return len(obj.child_ids) if obj.child_ids else 0
    
    def get_has_feedback(self, obj):
        return hasattr(obj, 'feedbacks') and obj.feedbacks.exists()


class MessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating messages"""
    model_id = serializers.UUIDField(required=False, allow_null=True)
    parent_message_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list
    )
    
    class Meta:
        model = Message
        fields = [
            'session', 'role', 'content', 'model_id',
            'parent_message_ids', 'participant', 'attachments'
        ]
    
    def validate_model_id(self, value):
        if value:
            try:
                AIModel.objects.get(id=value, is_active=True)
            except AIModel.DoesNotExist:
                raise serializers.ValidationError("Model not found or inactive")
        return value
    
    def validate_parent_message_ids(self, value):
        if value:
            # Verify all parent messages exist
            existing_ids = Message.objects.filter(
                id__in=value
            ).values_list('id', flat=True)
            
            missing_ids = set(value) - set(existing_ids)
            if missing_ids:
                raise serializers.ValidationError(
                    f"Parent messages not found: {missing_ids}"
                )
        return value
    
    def validate(self, attrs):
        session = attrs.get('session')
        
        # Validate participant for compare mode
        if session.mode == 'compare' and attrs.get('role') == 'assistant':
            if attrs.get('participant') not in ['a', 'b']:
                raise serializers.ValidationError(
                    "Participant must be 'a' or 'b' for assistant messages in compare mode"
                )
        
        # Auto-assign model based on participant
        if session.mode == 'direct' and attrs.get('role') == 'assistant':
            attrs['model_id'] = session.model_a_id
        elif session.mode == 'compare' and attrs.get('role') == 'assistant':
            if attrs.get('participant') == 'a':
                attrs['model_id'] = session.model_a_id
            elif attrs.get('participant') == 'b':
                attrs['model_id'] = session.model_b_id
        
        return attrs
    
    def create(self, validated_data):
        model_id = validated_data.pop('model_id', None)
        parent_ids = validated_data.pop('parent_message_ids', [])
        
        with transaction.atomic():
            # Set model
            if model_id:
                validated_data['model_id'] = model_id
            
            # Set parent IDs
            validated_data['parent_message_ids'] = parent_ids
            
            # Create message
            message = super().create(validated_data)
            
            # Update parent messages' child_ids
            if parent_ids:
                Message.objects.filter(id__in=parent_ids).update(
                    child_ids=F('child_ids') + [message.id]
                )
            
            # Create message relations
            for parent_id in parent_ids:
                MessageRelation.objects.create(
                    parent_id=parent_id,
                    child=message,
                    relation_type='reply'
                )
        
        return message


class MessageStreamSerializer(serializers.Serializer):
    """Serializer for streaming message creation"""
    id = serializers.UUIDField(required=False)
    content = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    role = serializers.CharField(required=True)
    parent_message_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list
    )
    modelId = serializers.CharField(required=False, allow_null=True)
    participant = serializers.CharField(required=False)
    status = serializers.ChoiceField(choices=['pending', 'streaming', 'success', 'failed'], required=True)
    temperature = serializers.FloatField(default=0.7, min_value=0, max_value=2)
    max_tokens = serializers.IntegerField(default=2000, min_value=1, max_value=8000)
    stream = serializers.BooleanField(default=True)
    audio_path = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    language = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    temp_image_url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    image_path = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    doc_path = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    temp_doc_url = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        role = attrs.get('role')
        content = attrs.get('content')
        model_id = attrs.get('modelId')
        audio_path = attrs.get('audio_path')
        language = attrs.get('language')
        if role == 'assistant':
            if model_id:
                try:
                    AIModel.objects.get(id=model_id, is_active=True)
                except AIModel.DoesNotExist:
                    raise serializers.ValidationError("Model not found or inactive")
                    # handle participant for compare mode

        if role != 'assistant' and not content:
            if not audio_path and not language:
                raise serializers.ValidationError({
                    'content': 'This field is required when role is not "assistant".'
                })

        return attrs


class MessageTreeSerializer(serializers.ModelSerializer):
    """Serializer for message tree structure"""
    children = serializers.SerializerMethodField()
    model_name = serializers.CharField(source='model.display_name', read_only=True)
    
    class Meta:
        model = Message
        fields = [
            'id', 'role', 'content', 'model_name', 'participant',
            'status', 'created_at', 'children', 'metadata'
        ]
    
    def get_children(self, obj):
        # Recursively serialize children
        if obj.child_ids:
            children = Message.objects.filter(id__in=obj.child_ids).order_by('position')
            return MessageTreeSerializer(children, many=True).data
        return []


class MessageRegenerateSerializer(serializers.Serializer):
    """Serializer for regenerating assistant messages"""
    temperature = serializers.FloatField(default=0.7, min_value=0, max_value=2)
    max_tokens = serializers.IntegerField(default=2000, min_value=1, max_value=8000)
    use_different_model = serializers.BooleanField(default=False)
    model_id = serializers.UUIDField(required=False)