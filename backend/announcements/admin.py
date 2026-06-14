from django.contrib import admin
from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    """公告管理后台"""

    list_display = [
        'title',
        'priority',
        'status',
        'is_pinned',
        'author',
        'view_count',
        'published_at',
        'created_at',
    ]
    list_filter = ['priority', 'status', 'is_pinned', 'created_at', 'published_at']
    search_fields = ['title', 'content']
    list_editable = ['status', 'is_pinned', 'priority']
    ordering = ['-is_pinned', '-created_at']
    readonly_fields = ['author', 'view_count', 'created_at', 'updated_at']

    fieldsets = (
        ('基本信息', {
            'fields': ('title', 'content', 'priority')
        }),
        ('发布设置', {
            'fields': ('status', 'is_pinned', 'published_at')
        }),
        ('统计信息', {
            'fields': ('author', 'view_count', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        """保存模型时设置作者"""
        if not change:  # 新建时设置作者
            obj.author = request.user
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        """获取只读字段"""
        readonly_fields = list(self.readonly_fields)
        if obj:  # 编辑模式下，作者不可修改
            readonly_fields.append('author')
        return readonly_fields
