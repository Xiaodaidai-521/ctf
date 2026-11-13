from pathlib import PurePosixPath
from rest_framework import serializers
from data_security.contracts import ProtectionError
from data_security.adapters.django.private_files import private_files
from data_security.adapters.django.protection_status import private_file_status
from data_security.runtime.storage import enabled as runtime_files_enabled
from .models import Resource
from .validators import validate_cover_image, validate_resource_file
from .validators import RESOURCE_FILE_TYPES
from users.serializers import UserSerializer


class ResourceSerializer(serializers.ModelSerializer):
    """资源序列化器"""
    uploader_info = UserSerializer(source='uploader', read_only=True)
    reviewer_info = UserSerializer(source='reviewer', read_only=True)
    tags_list = serializers.SerializerMethodField()
    resource_type_display = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_type = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    cover_image = serializers.SerializerMethodField()
    is_ai_highlighted = serializers.SerializerMethodField()
    ai_generated_label = serializers.SerializerMethodField()

    class Meta:
        model = Resource
        fields = [
            'id', 'title', 'description', 'resource_type', 'resource_type_display',
            'file_url', 'file_name', 'file_type', 'file_size', 'cover_image', 'cover_url',
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

    def to_representation(self, instance):
        result = super().to_representation(instance)
        owner = private_files('resources')
        result['protection'] = {'file': {'storage': 'legacy' if instance.file else 'unknown'},
                                'cover_image': {'storage': 'legacy' if instance.cover_image else 'empty'}}
        if runtime_files_enabled() and owner is None:
            result['protection'] = {name: getattr(instance, name).storage.protection_status(
                getattr(instance, name).name, verify=False) for name in ('file', 'cover_image')}
        request = self.context.get('request')
        if owner is not None and not isinstance(owner, ProtectionError) and request and request.user.is_authenticated:
            references = owner.authenticated_references(user=request.user, resource_id=instance.pk)
            result['protection'].update(private_file_status(owner, references))
        if owner is not None:
            result['cover_image'] = None
        return result

    def get_tags_list(self, obj):
        return obj.get_tags_list()

    def get_resource_type_display(self, obj):
        return dict(Resource.RESOURCE_TYPE_CHOICES).get(obj.resource_type, obj.resource_type)

    def get_file_url(self, obj):
        request = self.context.get('request')
        if request and not request.user.is_authenticated:
            return None
        owner = private_files('resources')
        if owner is not None:
            if isinstance(owner, ProtectionError) or not obj.private_files or not request or not request.user.is_authenticated:
                return None
            if obj.uploader_id != request.user.pk and not request.user.is_staff:
                return None
        elif not obj.file:
            return None
        path = f'/api/resources/{obj.id}/download/'
        if obj.is_tutoring_reserved and self.get_is_ai_highlighted(obj):
            path += f'?highlight_resource={obj.id}'
        return request.build_absolute_uri(path) if request else path

    def get_file_type(self, obj):
        # Expose a known extension, never a private storage directory or old
        # personally identifying upload filename.
        name = str(obj.file.name or '').lower()
        extension = '.tar.gz' if name.endswith('.tar.gz') else PurePosixPath(name).suffix
        return extension if extension in RESOURCE_FILE_TYPES else ''

    def get_file_name(self, obj):
        extension = self.get_file_type(obj)
        return f'resource-{obj.pk}{extension}' if extension else None

    def get_cover_url(self, obj):
        request = self.context.get('request')
        if request and not request.user.is_authenticated:
            return None
        owner = private_files('resources')
        if owner is not None:
            if self.get_file_url(obj) is None or 'cover_image' not in obj.private_files.get('files', {}):
                return None
            return self.context['request'].build_absolute_uri(f'/api/resources/{obj.id}/cover/download/')
        if obj.cover_image:
            request = self.context.get('request')
            path = f'/api/resources/{obj.id}/cover/download/'
            if obj.is_tutoring_reserved:
                path += f'?highlight_resource={obj.id}'
            return request.build_absolute_uri(path) if request else path
        return None

    def get_cover_image(self, obj):
        # Covers, including legacy bytes, use the permission-checked endpoint.
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
        if 'private_uploads' in self.context:
            uploads = self.context['private_uploads']
            if uploads is None:
                raise serializers.ValidationError('资源上传暂未开放。')
            result = uploads.create(validated_data, user=self.context['request'].user)
            if isinstance(result, ProtectionError):
                raise serializers.ValidationError('资源暂时无法保存。', code=result.code.value)
            return result

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
