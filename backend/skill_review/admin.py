from django.contrib import admin

from .models import (
    AssistanceRecord,
    DownstreamNotice,
    ManualReviewTask,
    ResultCorrection,
    RetestAssignment,
    ReviewCard,
    ScoreDispute,
    SubmissionErrorCause,
    SubmissionSnapshot,
    TeacherSamplingBatch,
    TeacherSamplingItem,
    VerificationResult,
)


@admin.register(AssistanceRecord)
class AssistanceRecordAdmin(admin.ModelAdmin):
    list_display = ('kind', 'level', 'source', 'shown', 'student', 'created_at')
    list_filter = ('kind', 'source', 'shown')


@admin.register(SubmissionSnapshot)
class SubmissionSnapshotAdmin(admin.ModelAdmin):
    list_display = ('submission_id', 'student', 'task', 'sequence', 'independence', 'first_effective', 'created_at')
    list_filter = ('independence', 'first_effective', 'assistance_tracking')
    readonly_fields = ('payload', 'payload_hash', 'assistance_snapshot')


@admin.register(VerificationResult)
class VerificationResultAdmin(admin.ModelAdmin):
    list_display = ('result_id', 'student', 'task', 'version', 'revision', 'program_status', 'manual_status', 'overall_status', 'is_current')
    list_filter = ('program_status', 'manual_status', 'overall_status', 'is_current', 'version')
    readonly_fields = ('program_result', 'manual_result', 'item_results')


@admin.register(ManualReviewTask)
class ManualReviewTaskAdmin(admin.ModelAdmin):
    list_display = ('review_id', 'student', 'task', 'status', 'claimed_by', 'reviewed_at')
    list_filter = ('status',)


@admin.register(SubmissionErrorCause)
class SubmissionErrorCauseAdmin(admin.ModelAdmin):
    list_display = ('submission', 'cause', 'status', 'source', 'confirmed_by')
    list_filter = ('cause', 'status', 'source')


@admin.register(ReviewCard)
class ReviewCardAdmin(admin.ModelAdmin):
    list_display = ('card_id', 'student', 'task', 'status', 'completed_at')
    list_filter = ('status',)


@admin.register(RetestAssignment)
class RetestAssignmentAdmin(admin.ModelAdmin):
    list_display = ('assignment_id', 'student', 'status', 'due_at', 'outcome', 'selected_task')
    list_filter = ('status', 'outcome')


@admin.register(TeacherSamplingBatch)
class TeacherSamplingBatchAdmin(admin.ModelAdmin):
    list_display = ('title', 'catalog', 'status', 'sample_size', 'high_risk_size', 'random_seed', 'deadline')
    list_filter = ('status',)
    readonly_fields = ('scope',)


@admin.register(TeacherSamplingItem)
class TeacherSamplingItemAdmin(admin.ModelAdmin):
    list_display = ('item_id', 'batch', 'selection_reason', 'status', 'claimed_by', 'reviewed_at')
    list_filter = ('selection_reason', 'status')


@admin.register(ScoreDispute)
class ScoreDisputeAdmin(admin.ModelAdmin):
    list_display = ('dispute_id', 'student', 'status', 'assigned_to', 'created_at')
    list_filter = ('status',)


@admin.register(ResultCorrection)
class ResultCorrectionAdmin(admin.ModelAdmin):
    list_display = ('correction_id', 'submission', 'source', 'corrected_by', 'created_at')
    list_filter = ('source',)
    readonly_fields = ('before', 'after')


@admin.register(DownstreamNotice)
class DownstreamNoticeAdmin(admin.ModelAdmin):
    list_display = ('target', 'status', 'target_connected', 'attempts', 'result', 'created_at')
    list_filter = ('target', 'status', 'target_connected')
    readonly_fields = ('payload',)
