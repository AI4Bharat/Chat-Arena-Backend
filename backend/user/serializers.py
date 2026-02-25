from rest_framework import serializers
from django.contrib.auth import get_user_model
from user.models import User
import uuid


class UserSerializer(serializers.ModelSerializer):
    """Full user serializer for authenticated requests"""
    class Meta:
        model = User
        fields = [
            'id', 'email', 'phone_number', 'display_name', 'auth_provider',
            'is_anonymous', 'created_at', 'updated_at',
            'is_active', 'preferences'
        ]
        read_only_fields = [
            'id', 'auth_provider', 'is_anonymous',
            'created_at', 'updated_at', 'firebase_uid'
        ]


class UserPublicSerializer(serializers.ModelSerializer):
    """Limited user info for public viewing"""
    class Meta:
        model = User
        fields = ['id', 'display_name']


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new users"""
    class Meta:
        model = User
        fields = [
            'email', 'display_name', 'auth_provider', 
            'firebase_uid', 'is_anonymous'
        ]
        
    def validate(self, attrs):
        # Validate based on auth provider
        if attrs.get('auth_provider') == 'google':
            if not attrs.get('email') or not attrs.get('firebase_uid'):
                raise serializers.ValidationError(
                    "Email and Firebase UID are required for Google auth"
                )
        elif attrs.get('auth_provider') == 'anonymous':
            attrs['is_anonymous'] = True
            attrs['email'] = None
            attrs['firebase_uid'] = None
            if not attrs.get('display_name'):
                attrs['display_name'] = f"Anonymous_{str(uuid.uuid4())[:8]}"
        
        return attrs


class UserPreferencesSerializer(serializers.Serializer):
    """Serializer for updating user preferences"""
    theme = serializers.CharField(required=False)
    language = serializers.CharField(required=False)
    default_model = serializers.UUIDField(required=False)
    show_model_names = serializers.BooleanField(required=False)
    enable_sound = serializers.BooleanField(required=False)
    auto_save_chat = serializers.BooleanField(required=False)
    
    def validate_theme(self, value):
        allowed_themes = ['light', 'dark', 'system']
        if value not in allowed_themes:
            raise serializers.ValidationError(
                f"Theme must be one of {allowed_themes}"
            )
        return value


class AnonymousAuthSerializer(serializers.Serializer):
    """Serializer for anonymous authentication"""
    display_name = serializers.CharField(required=False, max_length=255)
    
    def create(self, validated_data):
        display_name = validated_data.get('display_name')
        if not display_name:
            display_name = f"Anonymous_{str(uuid.uuid4())[:8]}"
            
        user = User.objects.create(
            display_name=display_name,
            auth_provider='anonymous',
            is_anonymous=True
        )
        return user


class GoogleAuthSerializer(serializers.Serializer):
    """Serializer for Google authentication"""
    id_token = serializers.CharField(required=True)
    
    def validate_id_token(self, value):
        # This will be validated in the view using Firebase Admin SDK
        return value


class PhoneAuthSerializer(serializers.Serializer):
    """Serializer for Phone authentication"""
    id_token = serializers.CharField(required=True)
    display_name = serializers.CharField(required=True, max_length=255)

    def validate_id_token(self, value):
        # This will be validated in the view using Firebase Admin SDK
        return value

    def validate_display_name(self, value):
        if not value or len(value.strip()) < 2:
            raise serializers.ValidationError(
                "Display name must be at least 2 characters long"
            )
        return value.strip()