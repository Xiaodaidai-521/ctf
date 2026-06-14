from rest_framework import serializers
from .models import Announcement
from users.models import CTFUser


class UserSimpleSerializer(serializers.ModelSerializer):
    """简单用户序列化器"""

    class Meta:
        model = CTFUser
        fields = ['id', 'username', 'nickname']



class AnnouncementSerializer(serializers.ModelSerializer):
    """公告序列化器"""

    author = UserSimpleSerializer(read_only=True)
    author_name = serializers.CharField(source='author.username', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Announcement
        fields = [
            'id',
            'title',
            'content',
            'priority',
            'priority_display',
            'status',
            'status_display',
            'is_pinned',
            'author',
            'author_name',
            'view_count',
            'created_at',
            'updated_at',
            'published_at',
        ]
        read_only_fields = ['author', 'view_count', 'created_at', 'updated_at', 'published_at']


class AnnouncementListSerializer(serializers.ModelSerializer):
    """公告列表序列化器"""

    author = UserSimpleSerializer(read_only=True)
    author_name = serializers.CharField(source='author.username', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = [
            'id',
            'title',
            'summary',
            'priority',
            'priority_display',
            'status',
            'status_display',
            'is_pinned',
            'author',
            'author_name',
            'view_count',
            'created_at',
            'updated_at',
            'published_at',
        ]

    def get_summary(self, obj):
        """获取内容摘要"""
        content = obj.content
        if len(content) > 100:
            return content[:100] + '...'
        return content


class AnnouncementCreateSerializer(serializers.ModelSerializer):
    """公告创建序列化器"""

    class Meta:
        model = Announcement
        fields = ['title', 'content', 'priority', 'status', 'is_pinned']

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class AnnouncementUpdateSerializer(serializers.ModelSerializer):
    """公告更新序列化器"""

    class Meta:
        model = Announcement
        fields = ['title', 'content', 'priority', 'status', 'is_pinned']
