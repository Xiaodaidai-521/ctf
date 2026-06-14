from django.contrib import admin
from .models import (
    LearningPath, PathModule, ModuleLab, UserPathProgress, UserModuleProgress,
    UserLabProgress, LabAttempt, KnowledgeConcept, ConceptRelation, ConceptResource,
    UserKnowledgeState, LearningPathRecommendation, ResourceRecommendation,
    UserLearningBehavior
)


@admin.register(LearningPath)
class LearningPathAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'slug', 'difficulty', 'total_modules', 'total_labs', 'estimated_hours', 'is_published', 'order', 'created_at']
    list_filter = ['difficulty', 'is_published', 'created_at']
    search_fields = ['title', 'slug', 'description']
    list_editable = ['order', 'is_published', 'difficulty']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PathModule)
class PathModuleAdmin(admin.ModelAdmin):
    list_display = ['id', 'learning_path', 'title', 'module_type', 'order', 'estimated_minutes', 'is_required', 'created_at']
    list_filter = ['module_type', 'is_required', 'learning_path', 'created_at']
    search_fields = ['title', 'description', 'learning_path__title']
    list_editable = ['order', 'is_required', 'module_type']
    filter_horizontal = ['requires_modules']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ModuleLab)
class ModuleLabAdmin(admin.ModelAdmin):
    list_display = ['id', 'module', 'lab', 'order', 'is_optional', 'created_at']
    list_filter = ['is_optional', 'created_at']
    search_fields = ['module__title', 'lab__title']
    list_editable = ['order', 'is_optional']


@admin.register(UserPathProgress)
class UserPathProgressAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'learning_path', 'progress_percentage', 'completed_modules', 'total_modules', 'started_at', 'last_accessed', 'completed_at']
    list_filter = ['learning_path', 'completed_at', 'started_at']
    search_fields = ['user__username', 'learning_path__title']
    readonly_fields = ['started_at', 'last_accessed', 'completed_at']


@admin.register(UserModuleProgress)
class UserModuleProgressAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'module', 'status', 'started_at', 'completed_at']

    search_fields = ['user__username', 'module__title']
    readonly_fields = ['started_at', 'completed_at']





@admin.register(LabAttempt)
class LabAttemptAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'lab', 'success', 'ip_address', 'timestamp']
    list_filter = ['success', 'timestamp']
    search_fields = ['user__username', 'lab__title']
    readonly_fields = ['timestamp', 'ip_address']


@admin.register(KnowledgeConcept)
class KnowledgeConceptAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'slug', 'concept_type', 'difficulty_level', 'importance', 'mitre_attack_id', 'cwe_id']
    list_filter = ['concept_type', 'difficulty_level', 'created_at']
    search_fields = ['name', 'slug', 'description', 'mitre_attack_id', 'cwe_id']
    list_editable = ['difficulty_level', 'importance']


@admin.register(ConceptRelation)
class ConceptRelationAdmin(admin.ModelAdmin):
    list_display = ['id', 'from_concept', 'relation_type', 'to_concept', 'strength', 'created_at']
    list_filter = ['relation_type', 'created_at']
    search_fields = ['from_concept__name', 'to_concept__name']
    list_editable = ['strength']


@admin.register(ConceptResource)
class ConceptResourceAdmin(admin.ModelAdmin):
    list_display = ['id', 'concept', 'content_type', 'object_id', 'role', 'weight', 'order']
    list_filter = ['role', 'content_type']
    search_fields = ['concept__name']
    list_editable = ['weight', 'order']


@admin.register(UserKnowledgeState)
class UserKnowledgeStateAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'concept', 'mastery_level', 'times_viewed', 'lab_successes', 'recall_probability', 'last_reviewed', 'next_review_at']
    list_filter = ['concept__concept_type', 'next_review_at', 'last_reviewed']
    search_fields = ['user__username', 'concept__name']
    readonly_fields = ['created_at', 'updated_at', 'last_reviewed', 'next_review_at']


@admin.register(LearningPathRecommendation)
class LearningPathRecommendationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'recommendation_type', 'score', 'expected_mastery_gain', 'is_accepted', 'generated_at']
    list_filter = ['recommendation_type', 'is_accepted', 'generated_at']
    search_fields = ['user__username', 'reasoning']
    filter_horizontal = ['covered_concepts']
    readonly_fields = ['generated_at', 'accepted_at']


@admin.register(ResourceRecommendation)
class ResourceRecommendationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'content_type', 'reason_type', 'score', 'impression_count', 'click_count', 'generated_at']
    list_filter = ['reason_type', 'generated_at']
    search_fields = ['user__username', 'reason_text']
    readonly_fields = ['generated_at']


@admin.register(UserLearningBehavior)
class UserLearningBehaviorAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'behavior_type', 'content_type', 'time_spent', 'success', 'score', 'timestamp']
    list_filter = ['behavior_type', 'success', 'timestamp']
    search_fields = ['user__username', 'session_id']
    filter_horizontal = ['concepts']
    readonly_fields = ['timestamp', 'ip_address']
