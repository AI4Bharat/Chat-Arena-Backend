from rest_framework import serializers
from django.db import transaction
from feedback.models import Feedback
from ai_model.models import AIModel
from chat_session.models import ChatSession
from message.models import Message
from ai_model.serializers import AIModelListSerializer
from feedback.services import FeedbackAnalyticsService
from chat_session.serializers import ChatSessionSerializer
from academic_prompts.models import AcademicPrompt


class FeedbackSerializer(serializers.ModelSerializer):
    """Full feedback serializer"""
    preferred_model = AIModelListSerializer(read_only=True)
    session_info = serializers.SerializerMethodField()
    message_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Feedback
        fields = [
            'id', 'user', 'session', 'message', 'feedback_type',
            'preferred_model', 'rating', 'categories', 'comment',
            'additional_feedback_json', 
            'has_image_input', 'has_audio_input', 'has_document_input', 'input_modality', 
            'created_at', 'session_info', 'message_info'
        ]
        read_only_fields = ['id', 'user', 'created_at']
    
    def get_session_info(self, obj):
        return {
            'id': str(obj.session.id),
            'mode': obj.session.mode,
            'title': obj.session.title
        }
    
    def get_message_info(self, obj):
        if obj.message:
            return {
                'id': str(obj.message.id),
                'role': obj.message.role,
                'content_preview': obj.message.content[:100]
            }
        return None


class FeedbackCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating feedback"""
    session_id = serializers.UUIDField(required=True, write_only=True)
    message_id = serializers.JSONField(required=True, write_only=True)
    preference = serializers.CharField(required=True, write_only=True)

    session_update = ChatSessionSerializer(source='session', read_only=True)

    class Meta:
        model = Feedback
        fields = [
            'id',
            'session_id', 'message_id', 'feedback_type',
            'preference', 'rating', 'categories', 'comment',
            'additional_feedback_json', 'session_update'
        ]
        read_only_fields = ['id']
    
    def to_representation(self, instance):
        """Customize the output to include session_update when needed."""
        data = super().to_representation(instance)
        session = instance.session
        should_include_session = False

        if (session.mode == 'random' or session.mode == 'academic') and session.feedbacks.count() == 1:
            should_include_session = True
        elif session.mode == 'academic' and instance.additional_feedback_json:
            should_include_session = True

        if not should_include_session:
            data.pop('session_update', None)
            
        return data
    
    def validate_rating(self, value):
        if value is not None and self.initial_data.get('feedback_type') != 'rating':
            raise serializers.ValidationError(
                "Rating is only valid for 'rating' feedback type"
            )
        return value
    
    def validate_categories(self, value):
        """Validate feedback categories"""
        valid_categories = [
            'accuracy', 'helpfulness', 'creativity', 'speed',
            'relevance', 'completeness', 'clarity', 'conciseness',
            'technical_accuracy', 'tone', 'formatting'
        ]
        
        if value:
            invalid_categories = set(value) - set(valid_categories)
            if invalid_categories:
                raise serializers.ValidationError(
                    f"Invalid categories: {invalid_categories}"
                )
        return value
    
    def validate(self, attrs):
        feedback_type = attrs.get('feedback_type')
        
        # Validate session exists and user has access
        try:
            session = ChatSession.objects.get(id=attrs['session_id'])
        except ChatSession.DoesNotExist:
            raise serializers.ValidationError("Session not found")
        
        # Check if user has access to the session
        user = self.context['request'].user
        if session.user != user and not session.is_public:
            raise serializers.ValidationError("You don't have access to this session")
        
        # Validate message if provided
        if attrs.get('message_id'):
            try:
                message = Message.objects.get(
                    id=attrs['message_id'],
                    session=session
                )
                attrs['message'] = message
            except Message.DoesNotExist:
                raise serializers.ValidationError("Message not found in session")
        
        # Type-specific validations
        if feedback_type == 'preference':
            if session.mode == 'direct':
                raise serializers.ValidationError(
                    "Preference feedback is only valid for compare mode sessions"
                )
                
        elif feedback_type == 'rating':
            if not attrs.get('rating'):
                raise serializers.ValidationError(
                    "Rating is required for rating feedback"
                )
                
        attrs['session'] = session
        return attrs
    
    def create(self, validated_data):
        # Remove the ID fields
        session = validated_data.pop('session', None)
        message = validated_data.pop('message', None)
        validated_data.pop('session_id', None)
        message_id = validated_data.pop('message_id', None)
        preference = validated_data.pop('preference', None)
        feedback_type = validated_data.get('feedback_type')
        user = self.context['request'].user

        try:
            userMessage = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            raise serializers.ValidationError("User Message not found")

        is_detailed_feedback = bool(validated_data.get('additional_feedback_json'))

        if feedback_type == 'preference' and not is_detailed_feedback:
            for modelMessage in userMessage.child_ids:
                modelMessageObj = Message.objects.get(id=modelMessage)
                if modelMessageObj.participant == 'a':
                    modelAId = str(modelMessageObj.model_id)
                elif modelMessageObj.participant == 'b':
                    modelBId = str(modelMessageObj.model_id)

            if preference == 'model_a':
                preferred_model_ids = [modelAId]
            elif preference == 'model_b':
                preferred_model_ids = [modelBId]
            elif preference == 'tie':
                preferred_model_ids = [modelAId, modelBId]
            else:
                preferred_model_ids = []

            validated_data['preferred_model_ids'] = preferred_model_ids

        # Automatically detect and set modality fields based on user message
        has_image = bool(userMessage.image_path)
        has_audio = bool(userMessage.audio_path)
        has_document = bool(userMessage.doc_path)
        
        validated_data['has_image_input'] = has_image
        validated_data['has_audio_input'] = has_audio
        validated_data['has_document_input'] = has_document
        
        # Determine primary modality
        modality_count = sum([has_image, has_audio, has_document])
        if modality_count > 1:
            validated_data['input_modality'] = 'multimodal'
        elif has_image:
            validated_data['input_modality'] = 'image'
        elif has_audio:
            validated_data['input_modality'] = 'audio'
        elif has_document:
            validated_data['input_modality'] = 'document'
        else:
            validated_data['input_modality'] = 'text'

        # Use update_or_create to handle both initial feedback and detailed feedback updates
        with transaction.atomic():
            feedback, created = Feedback.objects.update_or_create(
                user=user,
                session=session,
                message=userMessage,
                feedback_type=feedback_type,
                defaults=validated_data
            )

            message_update_fields = []

            # Update message feedback field when preference is provided
            if preference and not is_detailed_feedback:
                userMessage.feedback = preference
                message_update_fields.append('feedback')

            if is_detailed_feedback:
                userMessage.has_detailed_feedback = True
                message_update_fields.append('has_detailed_feedback')

                # For academic mode, increment the academic prompt's usage count on detailed feedback
                if session.mode == 'academic' and userMessage.metadata:
                    academic_prompt_id = userMessage.metadata.get('academic_prompt_id')
                    if academic_prompt_id:
                        try:
                            academic_prompt = AcademicPrompt.objects.select_for_update().get(id=academic_prompt_id)
                            academic_prompt.increment_usage()
                        except AcademicPrompt.DoesNotExist:
                            pass

            if message_update_fields:
                userMessage.save(update_fields=message_update_fields)

        # Trigger analytics update
        # FeedbackAnalyticsService.process_new_feedback(feedback)

        return feedback


class BulkFeedbackSerializer(serializers.Serializer):
    """Serializer for bulk feedback submission"""
    feedbacks = serializers.ListField(
        child=FeedbackCreateSerializer(),
        min_length=1,
        max_length=50
    )
    
    def create(self, validated_data):
        feedbacks_data = validated_data['feedbacks']
        created_feedbacks = []
        
        with transaction.atomic():
            for feedback_data in feedbacks_data:
                feedback_data['user'] = self.context['request'].user
                feedback = Feedback.objects.create(**feedback_data)
                created_feedbacks.append(feedback)
        
        # Process analytics for all feedbacks
        for feedback in created_feedbacks:
            FeedbackAnalyticsService.process_new_feedback(feedback)
        
        return created_feedbacks


class SessionFeedbackSummarySerializer(serializers.Serializer):
    """Serializer for session feedback summary"""
    session_id = serializers.UUIDField()
    total_feedback_count = serializers.IntegerField()
    average_rating = serializers.FloatField(allow_null=True)
    rating_distribution = serializers.DictField()
    preferences = serializers.DictField()
    categories_mentioned = serializers.DictField()
    recent_comments = serializers.ListField()


class ModelFeedbackStatsSerializer(serializers.Serializer):
    """Serializer for model feedback statistics"""
    model = AIModelListSerializer()
    total_ratings = serializers.IntegerField()
    average_rating = serializers.FloatField(allow_null=True)
    total_preferences = serializers.IntegerField()
    win_count = serializers.IntegerField()
    loss_count = serializers.IntegerField()
    win_rate = serializers.FloatField()
    categories_performance = serializers.DictField()