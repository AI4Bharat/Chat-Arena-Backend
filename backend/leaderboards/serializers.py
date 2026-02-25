from rest_framework import serializers

class UserContributorSerializer(serializers.Serializer):
    email = serializers.EmailField()
    display_name = serializers.CharField()
    chat_sessions_count = serializers.IntegerField()
    total_votes = serializers.IntegerField()
    votes_breakdown = serializers.DictField()
