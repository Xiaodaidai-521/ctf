from django.contrib import admin
from .models import (
    LearningDirection,
    StudentProfile,
    LearningPreference,
    LearningPersona,
)


@admin.register(LearningDirection)
class LearningDirectionAdmin(admin.ModelAdmin):
    list_display = ['id', 'key', 'label', 'sort_order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['key', 'label', 'description']
    ordering = ['sort_order', 'id']


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'onboarding_completed', 'created_at', 'updated_at']
    list_filter = ['onboarding_completed', 'created_at']
    search_fields = ['user__username', 'user__nickname', 'learning_goals']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(LearningPreference)
class LearningPreferenceAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'profile', 'preferred_pace', 'prefers_diagrams',
        'prefers_code_examples', 'daily_study_hours', 'difficulty_bias',
    ]
    list_filter = ['preferred_pace', 'prefers_diagrams', 'prefers_code_examples']
    search_fields = ['profile__user__username', 'profile__user__nickname']


@admin.register(LearningPersona)
class LearningPersonaAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'profile', 'persona_label', 'confidence_score', 'last_computed',
    ]
    list_filter = ['last_computed']
    search_fields = [
        'profile__user__username', 'profile__user__nickname', 'persona_label',
    ]
    readonly_fields = ['last_computed']
