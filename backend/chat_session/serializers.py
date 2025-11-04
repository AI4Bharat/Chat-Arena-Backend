from rest_framework import serializers
from django.utils import timezone
from chat_session.models import ChatSession
from user.serializers import UserPublicSerializer
from ai_model.serializers import AIModelListSerializer
from ai_model.models import AIModel
import secrets


class ChatSessionSerializer(serializers.ModelSerializer):
    """Full chat session serializer"""
    user = UserPublicSerializer(read_only=True)
    model_a = AIModelListSerializer(read_only=True)
    model_b = AIModelListSerializer(read_only=True)
    message_count = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()
    share_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatSession
        fields = [
            'id', 'user', 'mode', 'title', 'model_a', 'model_b',
            'is_public', 'share_token', 'created_at', 'updated_at',
            'metadata', 'expires_at', 'message_count', 'last_message_at',
            'share_url'
        ]
        read_only_fields = ['id', 'user', 'share_token', 'created_at', 'updated_at']
    
    def get_message_count(self, obj):
        return obj.messages.count()
    
    def get_last_message_at(self, obj):
        last_message = obj.messages.order_by('-created_at').first()
        return last_message.created_at if last_message else None
    
    def get_share_url(self, obj):
        if obj.share_token:
            request = self.context.get('request')
            if request:
                return f"{request.scheme}://{request.get_host()}/chat/shared/{obj.share_token}"
        return None


class ChatSessionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating chat sessions"""
    model_a_id = serializers.UUIDField(required=False, allow_null=True)
    model_b_id = serializers.UUIDField(required=False, allow_null=True)
    
    class Meta:
        model = ChatSession
        fields = ['mode', 'title', 'model_a_id', 'model_b_id', 'metadata']
    
    def validate(self, attrs):
        mode = attrs.get('mode')
        
        if mode == 'direct':
            if not attrs.get('model_a_id'):
                raise serializers.ValidationError(
                    "model_a_id is required for direct mode"
                )
            attrs['model_b_id'] = None
            
        elif mode == 'compare':
            if not attrs.get('model_a_id') or not attrs.get('model_b_id'):
                raise serializers.ValidationError(
                    "Both model_a_id and model_b_id are required for compare mode"
                )
            if attrs['model_a_id'] == attrs['model_b_id']:
                raise serializers.ValidationError(
                    "Cannot compare the same model"
                )
        
        elif mode == 'random':
            # Models will be selected automatically
            attrs['model_a_id'] = None
            attrs['model_b_id'] = None
        
        # Validate model IDs if provided
        if attrs.get('model_a_id'):
            try:
                attrs['model_a'] = AIModel.objects.get(
                    id=attrs['model_a_id'], 
                    is_active=True
                )
            except AIModel.DoesNotExist:
                raise serializers.ValidationError("Model A not found or inactive")
        
        if attrs.get('model_b_id'):
            try:
                attrs['model_b'] = AIModel.objects.get(
                    id=attrs['model_b_id'], 
                    is_active=True
                )
            except AIModel.DoesNotExist:
                raise serializers.ValidationError("Model B not found or inactive")
        
        return attrs
    
    def create(self, validated_data):
        # Remove the ID fields
        validated_data.pop('model_a_id', None)
        validated_data.pop('model_b_id', None)
        
        # Add user from request
        validated_data['user'] = self.context['request'].user
        
        # Set expiration for anonymous users
        if validated_data['user'].is_anonymous:
            validated_data['expires_at'] = validated_data['user'].anonymous_expires_at
        
        return super().create(validated_data)


class ChatSessionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing sessions"""
    model_a_name = serializers.CharField(source='model_a.display_name', read_only=True)
    model_b_name = serializers.CharField(source='model_b.display_name', read_only=True)
    message_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatSession
        fields = [
            'id', 'mode', 'title', 'model_a_name', 'model_b_name',
            'created_at', 'updated_at', 'message_count'
        ]
    
    def get_message_count(self, obj):
        # Use prefetch_related in view to optimize
        return getattr(obj, '_message_count', 0)


class ChatSessionShareSerializer(serializers.Serializer):
    """Serializer for sharing a session"""
    make_public = serializers.BooleanField(default=True)
    
    def update(self, instance, validated_data):
        instance.is_public = validated_data.get('make_public', True)
        if instance.is_public and not instance.share_token:
            instance.share_token = secrets.token_urlsafe(16)
        elif not instance.is_public:
            instance.share_token = None
        instance.save()
        return instance


class ChatSessionDuplicateSerializer(serializers.Serializer):
    """Serializer for duplicating a session"""
    include_messages = serializers.BooleanField(default=False)
    new_title = serializers.CharField(required=False, max_length=255)


class ChatSessionExportSerializer(serializers.Serializer):
    """Serializer for exporting session data"""
    format = serializers.ChoiceField(
        choices=['json', 'markdown', 'txt'],
        default='json'
    )
    include_metadata = serializers.BooleanField(default=False)
    include_timestamps = serializers.BooleanField(default=True)