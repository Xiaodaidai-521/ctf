from django.contrib import admin

from .models import (
    Capability,
    CapabilityState,
    CatalogVersion,
    DataBasisCard,
    DeliveryRegisterItem,
    DiagnosticQuestion,
    DiagnosticSession,
    KnowledgePoint,
    LegacyLabelMapping,
    PathChangeLog,
    RecommendationRun,
    TaskAttempt,
    TaskPackage,
    TeacherAdjustment,
    VerificationFact,
    WSTGMapping,
)


@admin.register(CatalogVersion)
class CatalogVersionAdmin(admin.ModelAdmin):
    list_display = ('version', 'label', 'status', 'rule_version', 'published_at')
    list_filter = ('status',)
    search_fields = ('version', 'label')


@admin.register(KnowledgePoint)
class KnowledgePointAdmin(admin.ModelAdmin):
    list_display = ('stable_id', 'name', 'track', 'catalog', 'sort_order')
    list_filter = ('track', 'catalog')
    search_fields = ('stable_id', 'name')


@admin.register(Capability)
class CapabilityAdmin(admin.ModelAdmin):
    list_display = ('stable_id', 'title', 'track', 'dimension', 'difficulty', 'status', 'course_order')
    list_filter = ('track', 'dimension', 'status', 'catalog')
    search_fields = ('stable_id', 'title')


@admin.register(LegacyLabelMapping)
class LegacyLabelMappingAdmin(admin.ModelAdmin):
    list_display = ('source_system', 'source_label', 'mapping_status', 'capability', 'catalog')
    list_filter = ('source_system', 'mapping_status')


@admin.register(WSTGMapping)
class WSTGMappingAdmin(admin.ModelAdmin):
    list_display = ('scenario_id', 'scenario_title', 'wstg_version', 'capability', 'status', 'reviewer')
    list_filter = ('status', 'wstg_version')


@admin.register(DataBasisCard)
class DataBasisCardAdmin(admin.ModelAdmin):
    list_display = ('card_id', 'source_title', 'capability', 'status', 'verified_date', 'owner')
    list_filter = ('status',)


@admin.register(TaskPackage)
class TaskPackageAdmin(admin.ModelAdmin):
    list_display = ('task_key', 'version', 'title', 'track', 'purpose', 'status', 'environment_available', 'requires_milestone_i')
    list_filter = ('track', 'purpose', 'status', 'environment_available', 'requires_milestone_i')
    search_fields = ('task_key', 'title')


@admin.register(DiagnosticQuestion)
class DiagnosticQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_key', 'version', 'track', 'capability', 'status')
    list_filter = ('track', 'status')


@admin.register(DiagnosticSession)
class DiagnosticSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'student', 'catalog', 'goal_track', 'status', 'started_at')
    list_filter = ('status', 'goal_track')


@admin.register(TaskAttempt)
class TaskAttemptAdmin(admin.ModelAdmin):
    list_display = ('attempt_id', 'student', 'task', 'status', 'claimed_at')
    list_filter = ('status',)


@admin.register(VerificationFact)
class VerificationFactAdmin(admin.ModelAdmin):
    list_display = ('fact_id', 'student', 'capability', 'outcome', 'independence', 'assistance_level', 'occurred_at')
    list_filter = ('outcome', 'independence', 'assistance_level')


@admin.register(CapabilityState)
class CapabilityStateAdmin(admin.ModelAdmin):
    list_display = ('student', 'capability', 'state', 'diagnosis_result', 'retest_due_at', 'updated_at')
    list_filter = ('state', 'diagnosis_result')


@admin.register(RecommendationRun)
class RecommendationRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'catalog', 'goal_track', 'rule_version', 'created_at')
    readonly_fields = ('input_snapshot', 'output')


@admin.register(PathChangeLog)
class PathChangeLogAdmin(admin.ModelAdmin):
    list_display = ('student', 'capability', 'from_state', 'to_state', 'reason', 'created_at')
    list_filter = ('to_state',)


@admin.register(TeacherAdjustment)
class TeacherAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'student', 'action', 'capability', 'task', 'status', 'created_at')
    list_filter = ('action', 'status')


@admin.register(DeliveryRegisterItem)
class DeliveryRegisterItemAdmin(admin.ModelAdmin):
    list_display = ('delivery_no', 'title', 'status', 'version', 'author', 'reviewer', 'signed_off_at')
    list_filter = ('status',)
