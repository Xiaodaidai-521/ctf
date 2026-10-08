from django.contrib import admin
from django.utils.html import format_html
from .models import Resource, ResourceCache


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    # 简化配置，先测试基本功能
    list_display = ['id', 'title', 'resource_type', 'category', 'status', 'is_tutoring_reserved', 'uploader', 'created_at']
    list_filter = ['status', 'is_tutoring_reserved']  # 先只保留状态筛选
    search_fields = ['title', 'description', 'uploader__username']
    # list_editable = ['status']  # 暂时禁用 inline editing
    readonly_fields = ['view_count', 'download_count', 'created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 20

    def get_queryset(self, request):
        """重写查询方法，确保显示所有数据"""
        return Resource.objects.all()

    def status_badge(self, obj):
        """显示状态徽章"""
        color_map = {
            'pending': '#faad14',
            'approved': '#52c41a',
            'rejected': '#ff4d4f',
        }
        color = color_map.get(obj.status, '#d9d9d9')
        status_map = {
            'pending': '待审核',
            'approved': '已通过',
            'rejected': '已拒绝',
        }
        status_text = status_map.get(obj.status, obj.status)
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{}</span>',
            color, status_text
        )
    status_badge.short_description = '状态标签'


@admin.register(ResourceCache)
class ResourceCacheAdmin(admin.ModelAdmin):
    list_display = ['id', 'studentId', 'knowledgePoint', 'studentLevel', 'cacheHitCount', 'updatedTime']
    list_filter = ['studentLevel']
    search_fields = ['studentId', 'knowledgePoint']
    readonly_fields = ['createdTime', 'updatedTime', 'cacheHitCount']
    ordering = ['-updatedTime']
