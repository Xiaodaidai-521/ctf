"""Serializers for legal compliance APIs."""

from rest_framework import serializers

from audit.models import AuditLedgerEntry

from .models import (
    ComplianceAgentRun,
    DataProcessingActivity,
    LegalAnalysisTask,
    LegalEvidence,
    LegalFactSnapshot,
    LegalProtocol,
    LegalProtocolVersion,
    LegalReport,
    LegalRiskFinding,
    UserConsentRecord,
    ViolationRecord,
)
from .services.consent_service import compute_content_hash


class ContainerAuditSerializer(serializers.Serializer):
    """Read-only serializer for Docker behavior audit events."""

    id = serializers.IntegerField(read_only=True)
    action = serializers.SerializerMethodField()
    container_id = serializers.SerializerMethodField()
    level = serializers.CharField(read_only=True)
    user = serializers.SerializerMethodField()
    challenge = serializers.SerializerMethodField()
    container_name = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    port = serializers.SerializerMethodField()
    network = serializers.SerializerMethodField()
    result = serializers.SerializerMethodField()
    error_message = serializers.SerializerMethodField()
    ledger_hash = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    def _detail(self, obj):
        return obj.detail or {}

    def get_action(self, obj):
        return self._detail(obj).get('action', '')

    def get_container_id(self, obj):
        detail = self._detail(obj)
        container = detail.get('container') or {}
        return detail.get('container_instance_id') or container.get('id')

    def get_user(self, obj):
        detail = self._detail(obj)
        user = detail.get('user') or {}
        return user.get('username') or getattr(obj.user, 'username', '') or '-'

    def get_challenge(self, obj):
        challenge = self._detail(obj).get('challenge') or {}
        return challenge.get('title') or '-'

    def get_container_name(self, obj):
        container = self._detail(obj).get('container') or {}
        return container.get('name') or '-'

    def get_image(self, obj):
        return self._detail(obj).get('image') or '-'

    def get_port(self, obj):
        return self._detail(obj).get('port')

    def get_network(self, obj):
        return self._detail(obj).get('network') or '-'

    def get_result(self, obj):
        return self._detail(obj).get('result') or '-'

    def get_error_message(self, obj):
        return self._detail(obj).get('error_message') or ''

    def get_ledger_hash(self, obj):
        ledger = AuditLedgerEntry.objects.filter(
            event_category='container',
            payload__audit_event_id=obj.id,
        ).order_by('-id').first()
        return ledger.current_hash if ledger else ''


class LegalProtocolSerializer(serializers.ModelSerializer):
    """Serializer for legal protocols."""

    latest_version = serializers.SerializerMethodField()

    class Meta:
        model = LegalProtocol
        fields = [
            'id',
            'key',
            'name',
            'protocol_type',
            'description',
            'is_active',
            'latest_version',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'latest_version', 'created_at', 'updated_at']

    def get_latest_version(self, obj):
        version = obj.versions.filter(is_published=True).order_by('-published_at', '-id').first()
        if not version:
            return None
        return {
            'id': version.id,
            'version': version.version,
            'title': version.title,
            'published_at': version.published_at,
            'effective_at': version.effective_at,
        }


class LegalProtocolVersionSerializer(serializers.ModelSerializer):
    """Serializer for protocol versions."""

    protocol_key = serializers.CharField(source='protocol.key', read_only=True)

    class Meta:
        model = LegalProtocolVersion
        fields = [
            'id',
            'protocol',
            'protocol_key',
            'version',
            'title',
            'content',
            'content_hash',
            'effective_at',
            'published_at',
            'source_url',
            'is_published',
            'created_by',
            'created_at',
        ]
        read_only_fields = ['id', 'protocol_key', 'content_hash', 'published_at', 'created_by', 'created_at']

    def validate(self, attrs):
        content = attrs.get('content')
        if content:
            attrs['content_hash'] = compute_content_hash(content)
        return attrs


class UserConsentRecordSerializer(serializers.ModelSerializer):
    """Serializer for user consent records."""

    protocol_key = serializers.CharField(source='protocol_version.protocol.key', read_only=True)
    protocol_name = serializers.CharField(source='protocol_version.protocol.name', read_only=True)
    version = serializers.CharField(source='protocol_version.version', read_only=True)

    class Meta:
        model = UserConsentRecord
        fields = [
            'id',
            'user',
            'protocol_version',
            'protocol_key',
            'protocol_name',
            'version',
            'consent_method',
            'evidence',
            'ip_address',
            'user_agent',
            'ledger_entry',
            'signed_at',
        ]
        read_only_fields = fields


class DataProcessingActivitySerializer(serializers.ModelSerializer):
    """Serializer for data processing activities."""

    class Meta:
        model = DataProcessingActivity
        fields = [
            'id',
            'name',
            'processing_type',
            'data_categories',
            'purpose',
            'legal_basis',
            'processor',
            'recipient',
            'retention_period',
            'risk_level',
            'metadata',
            'created_by',
            'ledger_entry',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'ledger_entry', 'created_at', 'updated_at']


class LegalEvidenceSerializer(serializers.ModelSerializer):
    """Serializer for legal evidence."""

    class Meta:
        model = LegalEvidence
        fields = [
            'id',
            'task',
            'risk_finding',
            'evidence_type',
            'object_type',
            'object_id',
            'title',
            'excerpt',
            'source_url',
            'relevance_score',
            'metadata',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class LegalRiskFindingSerializer(serializers.ModelSerializer):
    """Serializer for risk findings."""

    evidence_items = LegalEvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = LegalRiskFinding
        fields = [
            'id',
            'task',
            'title',
            'description',
            'severity',
            'likelihood',
            'impact',
            'score',
            'status',
            'recommendation',
            'evidence_items',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LegalAnalysisTaskSerializer(serializers.ModelSerializer):
    """Serializer for compliance analysis tasks."""

    risk_findings = LegalRiskFindingSerializer(many=True, read_only=True)

    class Meta:
        model = LegalAnalysisTask
        fields = [
            'id',
            'title',
            'source_type',
            'source_object_id',
            'input_text',
            'status',
            'created_by',
            'result_summary',
            'error_message',
            'metadata',
            'started_at',
            'completed_at',
            'created_at',
            'updated_at',
            'risk_findings',
        ]
        read_only_fields = [
            'id',
            'status',
            'created_by',
            'result_summary',
            'error_message',
            'started_at',
            'completed_at',
            'created_at',
            'updated_at',
            'risk_findings',
        ]


class ViolationRecordSerializer(serializers.ModelSerializer):
    """Serializer for violation records."""

    class Meta:
        model = ViolationRecord
        fields = [
            'id',
            'title',
            'description',
            'severity',
            'status',
            'related_task',
            'remediation_plan',
            'created_by',
            'ledger_entry',
            'occurred_at',
            'resolved_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'ledger_entry', 'created_at', 'updated_at']


class LegalReportSerializer(serializers.ModelSerializer):
    """Serializer for legal reports."""

    class Meta:
        model = LegalReport
        fields = [
            'id',
            'task',
            'report_type',
            'title',
            'summary',
            'content',
            'status',
            'generated_by',
            'ledger_entry',
            'metadata',
            'generated_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'generated_by', 'ledger_entry', 'generated_at', 'updated_at']


class ComplianceAgentRunSerializer(serializers.ModelSerializer):
    """Serializer for compliance agent runs."""

    class Meta:
        model = ComplianceAgentRun
        fields = [
            'id',
            'task',
            'agent_id',
            'provider',
            'model',
            'input_payload',
            'output_payload',
            'success',
            'error_message',
            'duration_ms',
            'created_at',
        ]
        read_only_fields = fields


class ExerciseFactPreviewRequestSerializer(serializers.Serializer):
    container_id = serializers.IntegerField(min_value=1)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        start = attrs.get('started_at')
        end = attrs.get('ended_at')
        if start and end and end < start:
            raise serializers.ValidationError('ended_at must not precede started_at')
        return attrs


class ExerciseFactConfirmSerializer(ExerciseFactPreviewRequestSerializer):
    preview_hash = serializers.CharField(min_length=64, max_length=64)
    manual_notes = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    title = serializers.CharField(required=False, allow_blank=True, max_length=200)
    run_analysis = serializers.BooleanField(required=False, default=True)


class LegalFactSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalFactSnapshot
        fields = [
            'id',
            'source_kind',
            'scope',
            'automated_facts',
            'manual_notes',
            'warnings',
            'evidence_refs',
            'preview_hash',
            'snapshot_hash',
            'extraction_version',
            'redaction_version',
            'analysis_task',
            'confirmed_by',
            'confirmed_at',
        ]
        read_only_fields = fields
