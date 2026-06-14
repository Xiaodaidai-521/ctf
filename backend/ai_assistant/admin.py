from django.contrib import admin
from .models import (
    AgentPreset,
    ChallengeKnowledgePack,
    CategoryKnowledgePack,
)


@admin.register(AgentPreset)
class AgentPresetAdmin(admin.ModelAdmin):
    list_display = ['id', 'preset_id', 'name', 'sort_order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['preset_id', 'name']
    ordering = ['sort_order', 'id']


@admin.register(ChallengeKnowledgePack)
class ChallengeKnowledgePackAdmin(admin.ModelAdmin):
    list_display = ['challenge', 'category_name', 'difficulty', 'pack_version', 'updated_at']
    list_filter = ['category_name', 'difficulty', 'pack_version']
    search_fields = ['challenge__title', 'category_name', 'summary']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(CategoryKnowledgePack)
class CategoryKnowledgePackAdmin(admin.ModelAdmin):
    list_display = ['category_name', 'pack_version', 'updated_at']
    search_fields = ['category_name', 'context_text']
    readonly_fields = ['created_at', 'updated_at']
