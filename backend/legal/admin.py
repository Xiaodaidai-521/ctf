"""Django admin for legal compliance models."""

from django.contrib import admin

from data_security.adapters.persistence.fields import field_storage_enabled
from users.permissions import authorized_users

from .services.data_access import authorized_legal_objects

from .models import (
    ComplianceAgentRun,
    DataProcessingActivity,
    LegalAnalysisTask,
    LegalEvidence,
    LegalProtocol,
    LegalProtocolVersion,
    LegalReport,
    LegalRiskFinding,
    UserConsentRecord,
    ViolationRecord,
)


class ProtectedLegalAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        queryset = authorized_legal_objects(super().get_queryset(request), request.user)
        if field_storage_enabled() and hasattr(self.model, 'encrypted_fields'):
            queryset = queryset.filter(security_state='sealed-v1')
        return queryset

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None and getattr(obj, 'security_state', 'legacy-v0') != 'legacy-v0':
            return (*fields, *obj.encrypted_fields)
        return fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if field_storage_enabled():
            if db_field.name in ('task', 'risk_finding'):
                kwargs['queryset'] = authorized_legal_objects(db_field.remote_field.model.objects.all(), request.user)
            elif db_field.name in ('created_by', 'generated_by'):
                kwargs['queryset'] = authorized_users(request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(LegalProtocol)
class LegalProtocolAdmin(admin.ModelAdmin):
    list_display = ['key', 'name', 'protocol_type', 'is_active', 'updated_at']
    list_filter = ['protocol_type', 'is_active']
    search_fields = ['key', 'name', 'description']


@admin.register(LegalProtocolVersion)
class LegalProtocolVersionAdmin(admin.ModelAdmin):
    list_display = ['protocol', 'version', 'title', 'is_published', 'published_at', 'created_by']
    list_filter = ['is_published', 'protocol']
    search_fields = ['protocol__key', 'title', 'content_hash']
    readonly_fields = ['content_hash', 'published_at', 'created_at']


@admin.register(UserConsentRecord)
class UserConsentRecordAdmin(admin.ModelAdmin):
    list_display = ['user', 'protocol_version', 'consent_method', 'signed_at', 'ledger_entry']
    list_filter = ['consent_method', 'signed_at']
    search_fields = ['user__username', 'protocol_version__protocol__key']
    readonly_fields = ['evidence', 'ledger_entry', 'signed_at']


@admin.register(DataProcessingActivity)
class DataProcessingActivityAdmin(admin.ModelAdmin):
    list_display = ['name', 'processing_type', 'risk_level', 'created_by', 'created_at']
    list_filter = ['processing_type', 'risk_level', 'created_at']
    search_fields = ['name', 'purpose', 'legal_basis']
    readonly_fields = ['ledger_entry', 'created_at', 'updated_at']


@admin.register(LegalAnalysisTask)
class LegalAnalysisTaskAdmin(ProtectedLegalAdmin):
    list_display = ['title', 'source_type', 'status', 'created_by', 'created_at', 'completed_at']
    list_filter = ['source_type', 'status', 'created_at']
    search_fields = ['title', 'result_summary']
    readonly_fields = ['started_at', 'completed_at', 'created_at', 'updated_at']


@admin.register(LegalRiskFinding)
class LegalRiskFindingAdmin(ProtectedLegalAdmin):
    list_display = ['title', 'task', 'severity', 'status', 'score', 'created_at']
    list_filter = ['severity', 'status', 'created_at']
    search_fields = ['title', 'description', 'recommendation']


@admin.register(LegalEvidence)
class LegalEvidenceAdmin(ProtectedLegalAdmin):
    list_display = ['title', 'evidence_type', 'object_type', 'object_id', 'relevance_score']
    list_filter = ['evidence_type']
    search_fields = ['title', 'excerpt', 'object_type', 'object_id']


@admin.register(ViolationRecord)
class ViolationRecordAdmin(admin.ModelAdmin):
    list_display = ['title', 'severity', 'status', 'created_by', 'created_at', 'resolved_at']
    list_filter = ['severity', 'status', 'created_at']
    search_fields = ['title', 'description', 'remediation_plan']
    readonly_fields = ['ledger_entry', 'created_at', 'updated_at']


@admin.register(LegalReport)
class LegalReportAdmin(ProtectedLegalAdmin):
    list_display = ['title', 'report_type', 'status', 'generated_by', 'generated_at']
    list_filter = ['report_type', 'status', 'generated_at']
    search_fields = ['title', 'summary']
    readonly_fields = ['ledger_entry', 'generated_at', 'updated_at']


@admin.register(ComplianceAgentRun)
class ComplianceAgentRunAdmin(ProtectedLegalAdmin):
    list_display = ['task', 'agent_id', 'provider', 'model', 'success', 'duration_ms', 'created_at']
    list_filter = ['agent_id', 'provider', 'success', 'created_at']
    search_fields = ['task__title', 'agent_id', 'provider', 'model']
    readonly_fields = ['input_payload', 'output_payload', 'created_at']
