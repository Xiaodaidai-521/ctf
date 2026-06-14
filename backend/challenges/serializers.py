from rest_framework import serializers

from .models import (
    Category,
    Challenge,
    ChallengeArticleRelation,
    ChallengeResourceRelation,
)


class CategorySerializer(serializers.ModelSerializer):
    """Category serializer."""

    challenge_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'challenge_count']

    def get_challenge_count(self, obj):
        return obj.challenge_set.filter(is_active=True).count()


class ChallengeArticleGuidanceSerializer(serializers.ModelSerializer):
    """Reading guidance serializer for related articles."""

    article_id = serializers.IntegerField(source='article.id', read_only=True)
    title = serializers.CharField(source='article.title', read_only=True)
    summary = serializers.CharField(source='article.summary', read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = ChallengeArticleRelation
        fields = ['article_id', 'title', 'summary', 'relation_type', 'reason', 'url']

    def get_url(self, obj):
        return f'/community/article/{obj.article_id}'


class ChallengeResourceGuidanceSerializer(serializers.ModelSerializer):
    """Reading guidance serializer for related resources."""

    resource_id = serializers.IntegerField(source='resource.id', read_only=True)
    title = serializers.CharField(source='resource.title', read_only=True)
    summary = serializers.CharField(source='resource.description', read_only=True)
    category = serializers.CharField(source='resource.category', read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = ChallengeResourceRelation
        fields = ['resource_id', 'title', 'summary', 'category', 'relation_type', 'reason', 'url']

    def get_url(self, obj):
        return f'/resources?resource={obj.resource_id}'


class ChallengeSerializer(serializers.ModelSerializer):
    """Challenge detail serializer."""

    category_name = serializers.CharField(source='category.name', read_only=True)
    is_solved = serializers.SerializerMethodField()
    user_id = serializers.SerializerMethodField()
    recommended_articles = serializers.SerializerMethodField()
    recommended_resources = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = [
            'id',
            'title',
            'description',
            'category',
            'category_name',
            'difficulty',
            'score',
            'hint',
            'attachment',
            'is_active',
            'solve_count',
            'is_solved',
            'user_id',
            'created_at',
            'docker_image',
            'redirect_port',
            'redirect_type',
            'recommended_articles',
            'recommended_resources',
        ]
        read_only_fields = ['id', 'solve_count', 'created_at']

    def get_is_solved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from submissions.models import Submission

            return Submission.objects.filter(
                user=request.user,
                challenge=obj,
                is_correct=True,
            ).exists()
        return False

    def get_user_id(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return request.user.id
        return None

    def get_recommended_articles(self, obj):
        relations = obj.article_guidance_relations.filter(
            is_active=True,
            article__status='approved',
        ).select_related('article').order_by('sort_order', 'id')
        return ChallengeArticleGuidanceSerializer(relations, many=True).data

    def get_recommended_resources(self, obj):
        relations = obj.resource_guidance_relations.filter(
            is_active=True,
            resource__status='approved',
        ).select_related('resource').order_by('sort_order', 'id')
        return ChallengeResourceGuidanceSerializer(relations, many=True).data


class ChallengeListSerializer(serializers.ModelSerializer):
    """Challenge list serializer."""

    category_name = serializers.CharField(source='category.name', read_only=True)
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)
    is_solved = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = [
            'id',
            'title',
            'description',
            'category_name',
            'difficulty',
            'difficulty_display',
            'score',
            'solve_count',
            'is_solved',
            'is_active',
            'docker_image',
            'redirect_port',
            'redirect_type',
        ]

    def get_is_solved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from submissions.models import Submission

            return Submission.objects.filter(
                user=request.user,
                challenge=obj,
                is_correct=True,
            ).exists()
        return False


class SubmissionSerializer(serializers.Serializer):
    """Flag submission serializer."""

    challenge_id = serializers.IntegerField(required=True)
    flag = serializers.CharField(required=True, max_length=200)
