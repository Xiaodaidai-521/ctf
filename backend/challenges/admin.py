from django.contrib import admin
from .models import (
    Category,
    Challenge,
    ChallengeRelation,
    ChallengeArticleRelation,
    ChallengeResourceRelation,
    ChallengeSolution,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """题目分类管理"""
    list_display = ['name', 'description', 'created_at']
    search_fields = ['name']


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    """CTF 题目管理"""
    list_display = ['title', 'category', 'difficulty', 'score', 'solve_count', 'is_active', 'created_at']
    list_filter = ['category', 'difficulty', 'is_active', 'created_at']
    search_fields = ['title', 'description', 'flag']
    ordering = ['category', 'score']

    fieldsets = (
        ('基本信息', {
            'fields': ('title', 'description', 'category', 'difficulty', 'score')
        }),
        ('题目设置', {
            'fields': ('flag', 'submission_mode', 'hint', 'attachment', 'is_active',
                       'docker_image', 'redirect_port', 'redirect_type')
        }),
        ('统计信息', {
            'fields': ('solve_count', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['solve_count', 'created_at', 'updated_at']


@admin.register(ChallengeSolution)
class ChallengeSolutionAdmin(admin.ModelAdmin):
    """题目预设解答管理"""
    list_display = ['challenge', 'answer_type', 'is_enabled', 'created_at']
    list_filter = ['answer_type', 'is_enabled']
    search_fields = ['challenge__title', 'content']
    
    fieldsets = (
        ('题目', {
            'fields': ('challenge',)
        }),
        ('解答设置', {
            'fields': ('answer_type', 'content', 'hint_map')
        }),
        ('开关', {
            'fields': ('is_enabled',)
        }),
    )


@admin.register(ChallengeRelation)
class ChallengeRelationAdmin(admin.ModelAdmin):
    """题目关联管理"""
    list_display = [
        'source_challenge',
        'relation_type',
        'target_challenge',
        'strength',
        'sort_order',
        'is_bidirectional',
        'is_active',
    ]
    list_filter = ['relation_type', 'is_bidirectional', 'is_active']
    search_fields = [
        'source_challenge__title',
        'target_challenge__title',
        'reason',
    ]
    ordering = ['source_challenge', 'sort_order', '-strength', 'id']


@admin.register(ChallengeArticleRelation)
class ChallengeArticleRelationAdmin(admin.ModelAdmin):
    """题目文章导读管理"""
    list_display = ['challenge', 'relation_type', 'article', 'sort_order', 'is_active']
    list_filter = ['relation_type', 'is_active']
    search_fields = ['challenge__title', 'article__title', 'reason']
    ordering = ['challenge', 'sort_order', 'id']


@admin.register(ChallengeResourceRelation)
class ChallengeResourceRelationAdmin(admin.ModelAdmin):
    """题目资源导读管理"""
    list_display = ['challenge', 'relation_type', 'resource', 'sort_order', 'is_active']
    list_filter = ['relation_type', 'is_active']
    search_fields = ['challenge__title', 'resource__title', 'reason']
    ordering = ['challenge', 'sort_order', 'id']
