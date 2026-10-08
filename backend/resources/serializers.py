from rest_framework import serializers
from .models import Resource
from .validators import validate_cover_image, validate_resource_file
from users.serializers import UserSerializer


class ResourceSerializer(serializers.ModelSerializer):
    """资源序列化器"""
    uploader_info = UserSerializer(source='uploader', read_only=True)
    reviewer_info = UserSerializer(source='reviewer', read_only=True)
    tags_list = serializers.SerializerMethodField()
    resource_type_display = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_url = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    is_ai_highlighted = serializers.SerializerMethodField()
    ai_generated_label = serializers.SerializerMethodField()

    class Meta:
        model = Resource
        fields = [
            'id', 'title', 'description', 'resource_type', 'resource_type_display',
            'file_url', 'file_size', 'cover_image', 'cover_url',
            'category', 'tags', 'tags_list', 'status', 'status_display',
            'is_tutoring_reserved', 'is_ai_highlighted', 'ai_generated_label',
            'uploader', 'uploader_info', 'reviewer', 'reviewer_info',
            'review_comment', 'view_count', 'download_count',
            'created_at', 'updated_at', 'reviewed_at'
        ]
        read_only_fields = [
            'id', 'view_count', 'download_count', 'uploader', 'reviewer',
            'reviewed_at', 'created_at', 'updated_at'
        ]

    def get_tags_list(self, obj):
        return obj.get_tags_list()

    def get_resource_type_display(self, obj):
        return dict(Resource.RESOURCE_TYPE_CHOICES).get(obj.resource_type, obj.resource_type)

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get('request')
        path = f'/api/resources/{obj.id}/download/'
        return request.build_absolute_uri(path) if request else path

    def get_cover_url(self, obj):
        if obj.cover_image:
            return obj.cover_image.url
        return None

    def get_is_ai_highlighted(self, obj):
        highlight_ids = self.context.get('highlight_resource_ids') or []
        if highlight_ids:
            return obj.id in highlight_ids or str(obj.id) in {str(item) for item in highlight_ids}
        return str(obj.id) == str(self.context.get('highlight_resource_id') or '')

    def get_ai_generated_label(self, obj):
        return 'AI多模态生成' if self.get_is_ai_highlighted(obj) else ''


class ResourceUploadSerializer(serializers.ModelSerializer):
    """资源上传序列化器"""
    class Meta:
        model = Resource
        fields = [
            'title', 'description', 'resource_type', 'file',
            'cover_image', 'category', 'tags', 'is_tutoring_reserved'
        ]

    def validate_file(self, value):
        return validate_resource_file(value)

    def validate_cover_image(self, value):
        return validate_cover_image(value)

    def create(self, validated_data):
        # 获取上传者
        validated_data['uploader'] = self.context['request'].user
        
        # 计算文件大小
        if 'file' in validated_data:
            validated_data['file_size'] = validated_data['file'].size
        
        # 设置默认状态为待审核
        validated_data['status'] = 'pending'
        
        return super().create(validated_data)


class ResourceReviewSerializer(serializers.Serializer):
    """资源审核序列化器"""
    resource_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=['approved', 'rejected'])
    review_comment = serializers.CharField(required=False, allow_blank=True)
