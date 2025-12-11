from rest_framework import serializers
from model_metrics.models import AIModel, ModelMetric
from message.models import Message


class AIModelSerializer(serializers.ModelSerializer):
    """Full AI Model serializer"""
    win_rate = serializers.SerializerMethodField()
    total_usage = serializers.SerializerMethodField()
    
    class Meta:
        model = AIModel
        fields = [
            'id', 'provider', 'model_name', 'model_code', 
            'display_name', 'description', 'capabilities',
            'max_tokens', 'supports_streaming', 'is_active',
            'created_at', 'win_rate', 'total_usage'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_win_rate(self, obj):
        """Calculate win rate from latest metrics"""
        latest_metric = obj.metrics.filter(
            category='overall',
            period='all_time'
        ).order_by('-calculated_at').first()
        
        if latest_metric and latest_metric.total_comparisons > 0:
            return round(latest_metric.win_rate, 2)
        return 0.0
    
    def get_total_usage(self, obj):
        """Get total usage count"""
        return Message.objects.filter(model=obj).count()


class AIModelListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing models"""
    class Meta:
        model = AIModel
        fields = [
            'id', 'provider', 'model_code', 'display_name',
            'capabilities', 'is_active', 'model_type'
        ]


class ModelMetricSerializer(serializers.ModelSerializer):
    """Model metrics serializer"""
    model_name = serializers.CharField(source='model.display_name', read_only=True)
    win_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = ModelMetric
        fields = [
            'id', 'model', 'model_name', 'category', 
            'total_comparisons', 'wins', 'losses', 'ties',
            'average_rating', 'elo_rating', 'win_rate',
            'period', 'calculated_at'
        ]
    
    def get_win_rate(self, obj):
        return round(obj.win_rate, 2)


class ModelComparisonSerializer(serializers.Serializer):
    """Serializer for model comparison requests"""
    model_a_id = serializers.UUIDField(required=True)
    model_b_id = serializers.UUIDField(required=True)
    messages = serializers.ListField(
        child=serializers.DictField(),
        required=True
    )
    temperature = serializers.FloatField(min_value=0, max_value=2, default=0.7)
    max_tokens = serializers.IntegerField(min_value=1, max_value=8000, default=2000)
    
    def validate_messages(self, value):
        """Validate message format"""
        for message in value:
            if 'role' not in message or 'content' not in message:
                raise serializers.ValidationError(
                    "Each message must have 'role' and 'content'"
                )
            if message['role'] not in ['system', 'user', 'assistant']:
                raise serializers.ValidationError(
                    "Role must be 'system', 'user', or 'assistant'"
                )
        return value
    
    def validate(self, data):
        """Validate models exist and are active"""
        try:
            model_a = AIModel.objects.get(id=data['model_a_id'], is_active=True)
            model_b = AIModel.objects.get(id=data['model_b_id'], is_active=True)
        except AIModel.DoesNotExist:
            raise serializers.ValidationError("One or both models not found or inactive")
        
        if model_a.id == model_b.id:
            raise serializers.ValidationError("Cannot compare a model with itself")
        
        data['model_a'] = model_a
        data['model_b'] = model_b
        return data


class ModelTestSerializer(serializers.Serializer):
    """Serializer for testing a model"""
    prompt = serializers.CharField(required=True)
    temperature = serializers.FloatField(min_value=0, max_value=2, default=0.7)
    max_tokens = serializers.IntegerField(min_value=1, max_value=8000, default=500)
    stream = serializers.BooleanField(default=True)


class ModelCapabilitySerializer(serializers.Serializer):
    """Serializer for model capabilities"""
    CAPABILITY_CHOICES = [
        'text', 'code', 'creative', 'reasoning', 
        'translation', 'summarization', 'conversation',
        'vision', 'function_calling', 'json_mode'
    ]
    
    capabilities = serializers.MultipleChoiceField(
        choices=CAPABILITY_CHOICES,
        required=False
    )