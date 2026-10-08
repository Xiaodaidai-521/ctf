"""API views for legal compliance workflows."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEvent
from audit.services import AuditLedgerService, canonical_json, sha256_hex

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
from .permissions import IsLegalAdmin, IsLegalReviewer
from .serializers import (
    ComplianceAgentRunSerializer,
    ContainerAuditSerializer,
    ExerciseFactConfirmSerializer,
    ExerciseFactPreviewRequestSerializer,
    LegalFactSnapshotSerializer,
    DataProcessingActivitySerializer,
    LegalAnalysisTaskSerializer,
    LegalEvidenceSerializer,
    LegalProtocolSerializer,
    LegalProtocolVersionSerializer,
    LegalReportSerializer,
    LegalRiskFindingSerializer,
    UserConsentRecordSerializer,
    ViolationRecordSerializer,
)
from .services.consent_service import ConsentService
from .services.compliance_orchestrator import ComplianceOrchestrator
from .services.exercise_fact_builder import ExerciseFactBuilder, ExerciseFactScope
from .services.fact_redactor import redact_manual_notes
from .services.fact_renderer import render_for_analysis
from .services.ledger_service import LegalLedgerService


class LegalProtocolViewSet(viewsets.ModelViewSet):
    """Manage legal protocols."""

    queryset = LegalProtocol.objects.all()
    serializer_class = LegalProtocolSerializer
    permission_classes = [IsLegalAdmin]


class LegalProtocolVersionViewSet(viewsets.ModelViewSet):
    """Manage protocol versions."""

    queryset = LegalProtocolVersion.objects.select_related('protocol', 'created_by')
    serializer_class = LegalProtocolVersionSerializer
    permission_classes = [IsLegalAdmin]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        protocol_version = self.get_object()
        protocol_version.is_published = True
        protocol_version.published_at = timezone.now()
        if not protocol_version.effective_at:
            protocol_version.effective_at = protocol_version.published_at
        protocol_version.save(update_fields=['is_published', 'published_at', 'effective_at'])
        AuditEvent.log(
            category='admin_action',
            summary=f'Published protocol version {protocol_version.id}',
            user=request.user,
            request=request,
            detail={'protocol_version_id': protocol_version.id},
        )
        AuditLedgerService.append_entry(
            event_category='consent_sign',
            object_type='legal.LegalProtocolVersion',
            object_id=protocol_version.id,
            actor=request.user,
            payload={
                'action': 'publish_protocol_version',
                'protocol_version_id': protocol_version.id,
                'protocol_id': protocol_version.protocol_id,
                'version': protocol_version.version,
                'content_hash': protocol_version.content_hash,
            },
        )
        return Response(self.get_serializer(protocol_version).data)


class UserConsentRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """Read user consent records and sign published protocol versions."""

    serializer_class = UserConsentRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff or getattr(self.request.user, 'role', '') == 'admin':
            return UserConsentRecord.objects.select_related(
                'user',
                'protocol_version',
                'protocol_version__protocol',
                'ledger_entry',
            )
        return UserConsentRecord.objects.filter(user=self.request.user).select_related(
            'protocol_version',
            'protocol_version__protocol',
            'ledger_entry',
        )

    @action(detail=False, methods=['get'])
    def my(self, request):
        queryset = self.get_queryset().filter(user=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def sign(self, request):
        protocol_version_id = request.data.get('protocol_version_id')
        if not protocol_version_id:
            return Response(
                {'error': 'protocol_version_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            protocol_version = LegalProtocolVersion.objects.select_related('protocol').get(
                id=protocol_version_id,
                is_published=True,
            )
        except LegalProtocolVersion.DoesNotExist:
            return Response(
                {'error': 'Protocol version does not exist or is not published'},
                status=status.HTTP_404_NOT_FOUND,
            )
        consent = ConsentService.sign_protocol(
            user=request.user,
            protocol_version=protocol_version,
            consent_method=request.data.get('consent_method', 'clickwrap'),
            evidence=request.data.get('evidence') or {},
            request=request,
        )
        return Response(self.get_serializer(consent).data, status=status.HTTP_201_CREATED)


class DataProcessingActivityViewSet(viewsets.ModelViewSet):
    """Manage data processing activity ledger."""

    queryset = DataProcessingActivity.objects.select_related('created_by', 'ledger_entry')
    serializer_class = DataProcessingActivitySerializer
    permission_classes = [IsLegalAdmin]

    def perform_create(self, serializer):
        activity = serializer.save(created_by=self.request.user)
        LegalLedgerService.attach_data_processing_ledger(activity, actor=self.request.user)


class LegalAnalysisTaskViewSet(viewsets.ModelViewSet):
    """Create and inspect compliance analysis tasks."""

    queryset = LegalAnalysisTask.objects.select_related('created_by').prefetch_related(
        'risk_findings',
        'risk_findings__evidence_items',
    )
    serializer_class = LegalAnalysisTaskSerializer
    permission_classes = [IsLegalReviewer]

    def perform_create(self, serializer):
        task = serializer.save(created_by=self.request.user)
        AuditEvent.log(
            category='legal_analysis',
            summary=f'Legal analysis task created: {task.title}',
            user=self.request.user,
            request=self.request,
            detail={'task_id': task.id, 'source_type': task.source_type},
        )
        AuditLedgerService.append_entry(
            event_category='legal_analysis',
            object_type='legal.LegalAnalysisTask',
            object_id=task.id,
            actor=self.request.user,
            payload={
                'action': 'create_analysis_task',
                'task_id': task.id,
                'title': task.title,
                'source_type': task.source_type,
                'source_object_id': task.source_object_id,
            },
        )

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        task = self.get_object()
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.result_summary = request.data.get('result_summary', task.result_summary)
        task.save(update_fields=['status', 'completed_at', 'result_summary', 'updated_at'])
        AuditEvent.log(
            category='legal_analysis',
            summary=f'Legal analysis task completed: {task.title}',
            user=request.user,
            request=request,
            detail={'task_id': task.id},
        )
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=['post'])
    def run_analysis(self, request, pk=None):
        task = self.get_object()
        result = ComplianceOrchestrator().run(task=task, actor=request.user)
        task = result['task']
        serializer = self.get_serializer(task)
        return Response({
            'task': serializer.data,
            'finding_id': result['finding'].id,
            'evidence_count': len(result['evidence']),
            'agent_run_id': result['agent_run'].id,
            'report_id': result['report'].id,
        })


class LegalRiskFindingViewSet(viewsets.ModelViewSet):
    """Manage risk findings."""

    queryset = LegalRiskFinding.objects.select_related('task').prefetch_related('evidence_items')
    serializer_class = LegalRiskFindingSerializer
    permission_classes = [IsLegalReviewer]


class LegalEvidenceViewSet(viewsets.ModelViewSet):
    """Manage legal evidence."""

    queryset = LegalEvidence.objects.select_related('task', 'risk_finding')
    serializer_class = LegalEvidenceSerializer
    permission_classes = [IsLegalReviewer]


class ViolationRecordViewSet(viewsets.ModelViewSet):
    """Manage compliance violation records."""

    queryset = ViolationRecord.objects.select_related('created_by', 'related_task', 'ledger_entry')
    serializer_class = ViolationRecordSerializer
    permission_classes = [IsLegalAdmin]

    def perform_create(self, serializer):
        record = serializer.save(created_by=self.request.user)
        LegalLedgerService.attach_violation_ledger(record, actor=self.request.user)


class LegalReportViewSet(viewsets.ModelViewSet):
    """Manage compliance reports."""

    queryset = LegalReport.objects.select_related('task', 'generated_by', 'ledger_entry')
    serializer_class = LegalReportSerializer
    permission_classes = [IsLegalReviewer]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'export']:
            return [IsLegalAdmin()]
        return [IsLegalReviewer()]

    def perform_create(self, serializer):
        report = serializer.save(generated_by=self.request.user)
        LegalLedgerService.attach_report_ledger(report, actor=self.request.user, action='generate')

    @action(detail=True, methods=['post'])
    def export(self, request, pk=None):
        report = self.get_object()
        report.status = 'exported'
        report.save(update_fields=['status', 'updated_at'])
        AuditEvent.log(
            category='report_export',
            summary=f'Legal report exported: {report.title}',
            user=request.user,
            request=request,
            detail={'report_id': report.id},
        )
        AuditLedgerService.append_entry(
            event_category='report_export',
            object_type='legal.LegalReport',
            object_id=report.id,
            actor=request.user,
            payload={
                'action': 'export_report',
                'report_id': report.id,
                'title': report.title,
                'status': report.status,
            },
        )
        return Response(self.get_serializer(report).data)


class ComplianceAgentRunViewSet(viewsets.ReadOnlyModelViewSet):
    """Read compliance agent execution traces."""

    queryset = ComplianceAgentRun.objects.select_related('task')
    serializer_class = ComplianceAgentRunSerializer
    permission_classes = [IsLegalReviewer]

    def get_queryset(self):
        queryset = super().get_queryset()
        task_id = self.request.query_params.get('task')
        success = self.request.query_params.get('success')
        provider = self.request.query_params.get('provider')
        if task_id:
            queryset = queryset.filter(task_id=task_id)
        if success is not None:
            queryset = queryset.filter(success=success.lower() == 'true')
        if provider:
            queryset = queryset.filter(provider=provider)
        return queryset.order_by('-created_at')


class ContainerAuditViewSet(viewsets.ReadOnlyModelViewSet):
    """Read Docker lifecycle audit evidence for compliance review."""

    serializer_class = ContainerAuditSerializer
    permission_classes = [IsLegalReviewer]

    def get_queryset(self):
        queryset = AuditEvent.objects.filter(category='container').select_related('user')
        user = self.request.query_params.get('user')
        challenge = self.request.query_params.get('challenge')
        action_name = self.request.query_params.get('action')
        level = self.request.query_params.get('level')
        if user:
            queryset = queryset.filter(user__username__icontains=user)
        if challenge:
            queryset = queryset.filter(detail__challenge__title__icontains=challenge)
        if action_name:
            queryset = queryset.filter(detail__action=action_name)
        if level:
            queryset = queryset.filter(level=level.upper())
        return queryset.order_by('-created_at')


def _fact_scope(validated_data):
    return ExerciseFactScope(
        container_id=validated_data['container_id'],
        started_at=validated_data.get('started_at'),
        ended_at=validated_data.get('ended_at'),
    )


class ExerciseFactPreviewView(APIView):
    """Build a read-only, redacted preview from one container session."""

    permission_classes = [IsLegalAdmin]

    def post(self, request):
        serializer = ExerciseFactPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            preview = ExerciseFactBuilder().build(
                scope=_fact_scope(serializer.validated_data),
                actor=request.user,
            )
        except DjangoValidationError as exc:
            return Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        AuditEvent.log(
            category='legal_analysis',
            summary='Exercise fact preview generated',
            user=request.user,
            request=request,
            detail={'container_id': serializer.validated_data['container_id']},
        )
        return Response(preview.to_dict())


class ExerciseFactConfirmView(APIView):
    """Confirm a snapshot, create its task, and optionally run analysis."""

    permission_classes = [IsLegalAdmin]

    def post(self, request):
        serializer = ExerciseFactConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            current = ExerciseFactBuilder().build(scope=_fact_scope(data), actor=request.user)
        except DjangoValidationError as exc:
            return Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        if current.preview_hash != data['preview_hash']:
            return Response(
                {'code': 'FACT_PREVIEW_CHANGED', 'preview': current.to_dict()},
                status=status.HTTP_409_CONFLICT,
            )
        notes = redact_manual_notes(data.get('manual_notes', ''))
        source_kind = 'hybrid' if notes else 'automated'
        snapshot_payload = {
            'scope': current.scope,
            'automated_facts': current.facts,
            'manual_notes': notes,
            'warnings': current.warnings,
            'evidence_refs': current.evidence_refs,
            'extraction_version': current.extraction_version,
            'redaction_version': current.redaction_version,
        }
        snapshot_hash = sha256_hex(canonical_json(snapshot_payload))
        with transaction.atomic():
            snapshot = LegalFactSnapshot.objects.create(
                source_kind=source_kind,
                scope=current.scope,
                automated_facts=current.facts,
                manual_notes=notes,
                warnings=current.warnings,
                evidence_refs=current.evidence_refs,
                preview_hash=current.preview_hash,
                snapshot_hash=snapshot_hash,
                extraction_version=current.extraction_version,
                redaction_version=current.redaction_version,
                confirmed_by=request.user,
            )
            AuditLedgerService.append_entry(
                event_category='exercise_fact_snapshot',
                object_type='legal.LegalFactSnapshot',
                object_id=snapshot.id,
                actor=request.user,
                payload={
                    'snapshot_id': snapshot.id,
                    'snapshot_hash': snapshot.snapshot_hash,
                    'scope': snapshot.scope,
                    'audit_event_ids': [item['audit_event_id'] for item in snapshot.evidence_refs],
                },
            )
            task = LegalAnalysisTask.objects.create(
                title=data.get('title') or f"{current.facts.get('challenge_title', '靶场')}做题过程合规审查",
                source_type='challenge',
                source_object_id=current.scope['challenge_id'],
                input_text=render_for_analysis(snapshot),
                metadata={
                    'entry': 'exercise_fact_snapshot',
                    'fact_snapshot_id': snapshot.id,
                    'snapshot_hash': snapshot.snapshot_hash,
                },
                created_by=request.user,
            )
            snapshot.analysis_task = task
            snapshot.save(update_fields=['analysis_task'])
            AuditEvent.log(
                category='legal_analysis',
                summary=f'Legal analysis task created from fact snapshot: {task.title}',
                user=request.user,
                request=request,
                detail={'task_id': task.id, 'fact_snapshot_id': snapshot.id},
            )
            AuditLedgerService.append_entry(
                event_category='legal_analysis',
                object_type='legal.LegalAnalysisTask',
                object_id=task.id,
                actor=request.user,
                payload={
                    'action': 'create_analysis_task_from_snapshot',
                    'task_id': task.id,
                    'fact_snapshot_id': snapshot.id,
                    'snapshot_hash': snapshot.snapshot_hash,
                },
            )
        result = None
        if data.get('run_analysis', True):
            result = ComplianceOrchestrator().run(task=task, actor=request.user)
        payload = LegalFactSnapshotSerializer(snapshot).data
        payload['task_id'] = task.id
        payload['analysis_status'] = result['task'].status if result else task.status
        return Response(payload, status=status.HTTP_201_CREATED)
