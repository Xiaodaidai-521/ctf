from rest_framework import serializers
from .models import Submission


class SubmissionSerializer(serializers.ModelSerializer):
    """提交记录序列化器"""
    username = serializers.CharField(source='user.username', read_only=True)
    user_nickname = serializers.CharField(source='user.nickname', read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    user_team = serializers.CharField(source='user.team', read_only=True)
    user_score = serializers.IntegerField(source='user.score', read_only=True)
    challenge_title = serializers.CharField(source='challenge.title', read_only=True)
    challenge_id = serializers.IntegerField(source='challenge.id', read_only=True)
    category_name = serializers.CharField(source='challenge.category.name', read_only=True)
    category_id = serializers.IntegerField(source='challenge.category.id', read_only=True)
    challenge_score = serializers.IntegerField(source='challenge.score', read_only=True)

    class Meta:
        model = Submission
        fields = ['id', 'username', 'user_nickname', 'user_id', 'user_team', 'user_score',
                 'challenge_title', 'challenge_id', 'category_name', 'category_id', 'challenge_score',
                 'flag', 'is_correct', 'ip_address', 'created_at']
        read_only_fields = ['id', 'user', 'is_correct', 'created_at']


class SubmissionCreateSerializer(serializers.Serializer):
    """创建提交序列化器"""
    challenge_id = serializers.IntegerField(required=True)
    flag = serializers.CharField(required=True, max_length=200)

    def validate_challenge_id(self, value):
        """验证题目是否存在且启用"""
        from challenges.models import Challenge
        try:
            challenge = Challenge.objects.get(id=value, is_active=True)
            return value
        except Challenge.DoesNotExist:
            raise serializers.ValidationError("题目不存在或未启用")

    def validate(self, attrs):
        """验证是否已提交过正确的答案"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from submissions.models import Submission
            existing = Submission.objects.filter(
                user=request.user,
                challenge_id=attrs['challenge_id'],
                is_correct=True
            ).exists()
            if existing:
                raise serializers.ValidationError("您已成功解决此题")
        return attrs
