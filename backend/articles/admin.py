from django.contrib import admin
from .models import Article, Category, Comment, ArticleLike, CommentLike, ArticleCollect


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon', 'order', 'created_at']
    list_editable = ['order', 'icon']
    search_fields = ['name', 'description']


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    # 简化配置，先测试基本功能
    list_display = ['id', 'title', 'author', 'category', 'status', 'created_at']
    list_filter = ['status']  # 先只保留状态筛选
    search_fields = ['title', 'content', 'author__username']
    # list_editable = ['status']  # 暂时禁用 inline editing
    readonly_fields = ['view_count', 'like_count', 'comment_count', 'collect_count', 'created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 20

    def get_queryset(self, request):
        """重写查询方法，确保显示所有数据"""
        return Article.objects.all()

    def status_badge(self, obj):
        """显示状态徽章"""
        color_map = {
            'draft': '#d9d9d9',
            'published': '#52c41a',
            'pending': '#faad14',
            'rejected': '#ff4d4f',
        }
        color = color_map.get(obj.status, '#d9d9d9')
        status_map = {
            'draft': '草稿',
            'published': '已发布',
            'pending': '待审核',
            'rejected': '已拒绝',
        }
        status_text = status_map.get(obj.status, obj.status)
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{}</span>',
            color, status_text
        )
    status_badge.short_description = '状态标签'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'article', 'author', 'parent', 'like_count', 'created_at']
    list_filter = ['article', 'created_at']
    search_fields = ['content', 'author__username', 'article__title']
    readonly_fields = ['created_at', 'like_count']


@admin.register(ArticleLike)
class ArticleLikeAdmin(admin.ModelAdmin):
    list_display = ['article', 'user', 'created_at']
    list_filter = ['created_at']
    search_fields = ['article__title', 'user__username']


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ['comment', 'user', 'created_at']
    list_filter = ['created_at']


@admin.register(ArticleCollect)
class ArticleCollectAdmin(admin.ModelAdmin):
    list_display = ['article', 'user', 'created_at']
    list_filter = ['created_at']
