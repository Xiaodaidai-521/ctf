from django.contrib import admin

from .models import (
    FeedbackAccessLog,
    FeedbackAction,
    FeedbackAttachment,
    FeedbackEventLink,
    FeedbackEvidence,
    FeedbackReferral,
    FeedbackRelation,
    FeedbackReview,
    FeedbackSamplingBatch,
    FeedbackSamplingItem,
    FeedbackTicket,
)


@admin.register(FeedbackTicket)
class FeedbackTicketAdmin(admin.ModelAdmin):
    list_display = ('feedback_id', 'category', 'issue_type', 'status', 'student', 'owner', 'created_at')
    list_filter = ('category', 'status', 'impact_level', 'novelty', 'conflict_flag')
    search_fields = ('feedback_id', 'student__username', 'submitter__username', 'dispute')
    readonly_fields = ('feedback_id', 'created_at', 'updated_at')


@admin.register(FeedbackEvidence)
class FeedbackEvidenceAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'slot', 'status', 'source', 'visibility', 'is_current', 'created_at')
    list_filter = ('status', 'source', 'visibility', 'is_current')


@admin.register(FeedbackAction)
class FeedbackActionAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'action', 'from_status', 'to_status', 'actor', 'ticket_version', 'created_at')
    list_filter = ('action', 'actor_role', 'visibility')
    readonly_fields = [field.name for field in FeedbackAction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FeedbackReview)
class FeedbackReviewAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'conclusion', 'reviewer', 'is_current', 'ticket_version', 'created_at')
    list_filter = ('conclusion', 'is_current')
    readonly_fields = [field.name for field in FeedbackReview._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(FeedbackAttachment)
admin.site.register(FeedbackReferral)
admin.site.register(FeedbackRelation)
admin.site.register(FeedbackSamplingBatch)
admin.site.register(FeedbackSamplingItem)
admin.site.register(FeedbackAccessLog)
admin.site.register(FeedbackEventLink)
