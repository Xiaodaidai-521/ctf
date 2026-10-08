from django.contrib import admin
from .models import (
    LearningDirection,
    StudentProfile,
    LearningPreference,
    LearningPersona,
    OnboardingInterview,
    StudentProfileReport,
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
        'id', 'profile', 'source_report', 'persona_label', 'confidence_score', 'last_computed',
    ]
    list_filter = ['last_computed']
    search_fields = [
        'profile__user__username', 'profile__user__nickname', 'persona_label',
    ]
    readonly_fields = ['last_computed']

@admin.register(OnboardingInterview)
class OnboardingInterviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'profile', 'status', 'current_question', 'generation_provider', 'updated_at']
    list_filter = ['status', 'generation_provider']
    search_fields = ['profile__user__username', 'profile__user__nickname']
    readonly_fields = ['started_at', 'completed_at', 'updated_at']


@admin.register(StudentProfileReport)
class StudentProfileReportAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'profile', 'source_interview', 'report_type', 'version',
        'generation_status', 'generation_provider', 'created_at',
    ]
    list_filter = ['report_type', 'generation_status', 'generation_provider', 'created_at']
    search_fields = ['profile__user__username', 'profile__user__nickname', 'summary']
    readonly_fields = ['input_signature', 'created_at']
