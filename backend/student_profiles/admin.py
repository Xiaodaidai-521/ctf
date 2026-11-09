from django.contrib import admin
from django.utils import timezone
from data_security.adapters.persistence.fields import field_storage_enabled
from users.models import CourseDataGrant
from users.permissions import authorized_users
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


class CourseScopeFilter(admin.SimpleListFilter):
    title = '授权课程'
    parameter_name = 'course'

    def lookups(self, request, model_admin):
        return CourseDataGrant.objects.filter(actor=request.user, active=True,
            expires_at__gt=timezone.now()).values_list('course_id', 'course__title').distinct()

    def queryset(self, request, queryset):
        return queryset


class ProfileDataAdmin(admin.ModelAdmin):
    owner_lookup = 'profile__user'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if field_storage_enabled():
            course_id = request.GET.get('course')
            if course_id is not None and not course_id.isdecimal():
                return queryset.none()
            queryset = queryset.filter(**{self.owner_lookup + '__in': authorized_users(request.user, course_id)})
        return queryset

    def get_list_filter(self, request):
        filters = super().get_list_filter(request)
        return (*filters, CourseScopeFilter) if field_storage_enabled() else filters

    def get_exclude(self, request, obj=None):
        excluded = super().get_exclude(request, obj)
        if field_storage_enabled() or obj is not None and obj.security_state != 'legacy-v0':
            return (*(excluded or ()), *self.model.encrypted_fields)
        return excluded

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if field_storage_enabled():
            course_id = request.GET.get('course')
            allowed = authorized_users(request.user, course_id if course_id and course_id.isdecimal() else None)
            if db_field.name == 'user':
                kwargs['queryset'] = allowed
            elif db_field.name in ('profile', 'source_report', 'source_interview'):
                lookup = 'user__in' if db_field.name == 'profile' else 'profile__user__in'
                kwargs['queryset'] = db_field.remote_field.model.objects.filter(**{lookup: allowed})
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(StudentProfile)
class StudentProfileAdmin(ProfileDataAdmin):
    owner_lookup = 'user'
    list_display = ['id', 'user', 'onboarding_completed', 'created_at', 'updated_at']
    list_filter = ['onboarding_completed', 'created_at']
    search_fields = ['user__username', 'user__nickname', 'learning_goals']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(LearningPreference)
class LearningPreferenceAdmin(ProfileDataAdmin):
    list_display = [
        'id', 'profile', 'preferred_pace', 'prefers_diagrams',
        'prefers_code_examples', 'daily_study_hours', 'difficulty_bias',
    ]
    list_filter = ['preferred_pace', 'prefers_diagrams', 'prefers_code_examples']
    search_fields = ['profile__user__username', 'profile__user__nickname']


@admin.register(LearningPersona)
class LearningPersonaAdmin(ProfileDataAdmin):
    list_display = [
        'id', 'profile', 'source_report', 'persona_label', 'confidence_score', 'last_computed',
    ]
    list_filter = ['last_computed']
    search_fields = [
        'profile__user__username', 'profile__user__nickname', 'persona_label',
    ]
    readonly_fields = ['last_computed']

@admin.register(OnboardingInterview)
class OnboardingInterviewAdmin(ProfileDataAdmin):
    list_display = ['id', 'profile', 'status', 'current_question', 'generation_provider', 'updated_at']
    list_filter = ['status', 'generation_provider']
    search_fields = ['profile__user__username', 'profile__user__nickname']
    readonly_fields = ['started_at', 'completed_at', 'updated_at']


@admin.register(StudentProfileReport)
class StudentProfileReportAdmin(ProfileDataAdmin):
    list_display = [
        'id', 'profile', 'source_interview', 'report_type', 'version',
        'generation_status', 'generation_provider', 'created_at',
    ]
    list_filter = ['report_type', 'generation_status', 'generation_provider', 'created_at']
    search_fields = ['profile__user__username', 'profile__user__nickname', 'summary']
    readonly_fields = ['input_signature', 'created_at']
