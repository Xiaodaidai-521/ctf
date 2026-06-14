from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Article, Category, Comment, ArticleLike, CommentLike, ArticleCollect

User = get_user_model()


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'icon', 'order']


class AuthorSerializer(serializers.ModelSerializer):
    avatar_url = serializers.ImageField(source='avatar', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'nickname', 'avatar_url']


class ArticleListSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    tags_list = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            'id', 'title', 'author', 'category', 'category_name',
            'tags', 'tags_list', 'cover', 'summary',
            'view_count', 'like_count', 'comment_count', 'collect_count',
            'is_recommend', 'is_top', 'created_at', 'published_at'
        ]

    def get_tags_list(self, obj):
        return obj.tags_list


class ArticleDetailSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    tags_list = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_collected = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            'id', 'title', 'content', 'author', 'category',
            'tags', 'tags_list', 'cover', 'summary', 'status',
            'view_count', 'like_count', 'comment_count', 'collect_count',
            'is_recommend', 'is_top', 'is_liked', 'is_collected',
            'created_at', 'updated_at', 'published_at'
        ]

    def get_tags_list(self, obj):
        return obj.tags_list

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return ArticleLike.objects.filter(article=obj, user=request.user).exists()
        return False

    def get_is_collected(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return ArticleCollect.objects.filter(article=obj, user=request.user).exists()
        return False


class ArticleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ['title', 'content', 'category', 'tags', 'cover', 'summary']

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        validated_data['status'] = 'pending'  # 新文章默认待审核
        return super().create(validated_data)


class ArticleUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ['title', 'content', 'category', 'tags', 'cover', 'summary']

    def update(self, instance, validated_data):
        # 如果文章已发布，更新后重新进入待审核状态
        if instance.status == 'approved':
            validated_data['status'] = 'pending'
        return super().update(instance, validated_data)


class ArticleReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['approved', 'rejected'])
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class CommentAuthorSerializer(serializers.ModelSerializer):
    avatar_url = serializers.ImageField(source='avatar', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'nickname', 'avatar_url']


class CommentSerializer(serializers.ModelSerializer):
    author = CommentAuthorSerializer(read_only=True)
    is_liked = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id', 'article', 'author', 'parent', 'content',
            'like_count', 'is_liked', 'replies', 'created_at'
        ]

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return CommentLike.objects.filter(comment=obj, user=request.user).exists()
        return False

    def get_replies(self, obj):
        # 获取所有一级回复
        replies = obj.replies.all()[:5]  # 限制显示5条
        return CommentSerializer(replies, many=True, context=self.context).data


class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['article', 'parent', 'content']

    def validate(self, data):
        # 验证父评论是否属于同一篇文章
        parent = data.get('parent')
        article = data.get('article')
        if parent and parent.article != article:
            raise serializers.ValidationError('父评论必须属于同一篇文章')
        return data

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class ArticleHotSerializer(serializers.Serializer):
    """热度排行序列化器"""
    id = serializers.IntegerField()
    title = serializers.CharField()
    author = AuthorSerializer()
    view_count = serializers.IntegerField()
    like_count = serializers.IntegerField()
    comment_count = serializers.IntegerField()
    heat_score = serializers.FloatField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return data
