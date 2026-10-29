from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import ChallengeMapping, LabAssignment
from .policy import AUP, AUP_VERSION


def fields(data, allowed, required=()):
    if not isinstance(data, dict) or set(data) - set(allowed) or set(required) - set(data):
        raise ValidationError('字段缺失或包含未授权字段。')
    return data


def assignment_payload(assignment):
    scope = {key: value for key, value in assignment.scope.items()
             if key not in ('verifier_endpoint', 'repair_task_hash')}
    usable = (assignment.state == 'active' and assignment.baseline_observed_at
              and assignment.expires_at > timezone.now() and not assignment.mapping.paused)
    if not usable:
        scope['target'] = ''
    return {
        'assignment_id': str(assignment.assignment_id), 'attempt_id': str(assignment.attempt.attempt_id),
        'task_id': assignment.attempt.task_id, 'task_version': assignment.attempt.task_version,
        'state': assignment.state, 'expires_at': assignment.expires_at, 'scope': scope,
        'policy': assignment.policy, 'physical_cleanup': assignment.physical_cleanup,
        'materials': assignment.attempt.task.materials,
        'acceptance': assignment.attempt.task.acceptance,
        'evidence': [{'evidence_id': str(row.evidence_id), 'status': row.status,
                      'error': row.error, 'verifier_version': row.verifier_version,
                      'result_id': str(row.result.result_id) if row.result_id else None}
                     for row in assignment.evidence.select_related('result').all()],
    }


class AuditedView(APIView):
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, APIException) and self.request.user.is_authenticated:
            services.audit(self.request.user, 'denied', reason=exc.__class__.__name__)
        return super().handle_exception(exc)


def evidence_payload(row):
    return {'evidence_id': str(row.evidence_id), 'status': row.status, 'error': row.error,
            'verifier_version': row.verifier_version, 'observed_at': row.observed_at,
            'content_hash': row.content_hash, 'source': row.source,
            'result_id': str(row.result.result_id) if row.result_id else None,
            'submission_id': str(row.result.submission.submission_id) if row.result_id else None,
            'module1_fact_ids': row.result.module1_fact_ids if row.result_id else {}}


class StartView(AuditedView):
    def post(self, request, assignment_id):
        from .evidence import start
        fields(request.data, ())
        assignment = services.owned_assignment(request.user, assignment_id, write=True)
        started = start(assignment)
        if started is None:
            return Response({'status': 'baseline_unavailable', 'retryable': True}, status=503)
        return Response(assignment_payload(started))


class VerifyView(AuditedView):
    def post(self, request, assignment_id):
        from .evidence import verify_challenge
        fields(request.data, ('key',), ('key',))
        assignment = services.owned_assignment(request.user, assignment_id, write=True)
        row, created = verify_challenge(assignment=assignment, key=request.data['key'])
        return Response(evidence_payload(row), status=201 if created else 200)


class EvidenceView(AuditedView):
    def get(self, request, assignment_id, evidence_id):
        assignment = services.owned_assignment(request.user, assignment_id)
        row = get_object_or_404(assignment.evidence, evidence_id=evidence_id)
        return Response(evidence_payload(row))


class SelfReportView(AuditedView):
    @transaction.atomic
    def post(self, request, assignment_id):
        fields(request.data, ())
        assignment = services.owned_assignment(request.user, assignment_id, write=True)
        services.active_assignment(assignment)
        services.audit(request.user, 'student_self_report', assignment)
        return Response({'verified': False, 'detail': '仅登记辅助自报，仍须服务端核验。'})


def claim_payload(claim):
    return {'claim_id': str(claim.claim_id), 'attempt_id': str(claim.attempt.attempt_id),
            'retest_id': str(claim.retest.assignment_id), 'completed': claim.completed,
            'status': claim.evidence.status if claim.evidence_id else 'pending_independent_verification',
            'evidence_id': str(claim.evidence.evidence_id) if claim.evidence_id else None,
            'scope': 'proposal_only_not_live_juice_patch'}


class RepairView(AuditedView):
    def get(self, request, assignment_id):
        assignment = services.owned_assignment(request.user, assignment_id)
        return Response({'task_id': assignment.mapping.repair_task_id,
                         'materials': assignment.mapping.repair_task.materials,
                         'claims': [claim_payload(claim) for claim in assignment.repair_claims.all()]})

    def post(self, request, assignment_id):
        from .repairs import submit_claim
        fields(request.data, ('key', 'explanation', 'policy'), ('key', 'explanation', 'policy'))
        assignment = services.owned_assignment(request.user, assignment_id, write=True)
        claim, created = submit_claim(assignment=assignment, **request.data)
        return Response(claim_payload(claim), status=201 if created else 200)


class RepairVerifyView(AuditedView):
    def post(self, request, assignment_id, claim_id):
        from .repairs import verify_claim
        fields(request.data, ('key',), ('key',))
        assignment = services.owned_assignment(request.user, assignment_id, write=True)
        row, created = verify_claim(assignment=assignment, claim_id=claim_id, key=request.data['key'])
        return Response(evidence_payload(row), status=201 if created else 200)


class ReviewView(AuditedView):
    def put(self, request, assignment_id):
        from .review import complete_review
        assignment = services.owned_assignment(request.user, assignment_id, write=True)
        card = complete_review(assignment=assignment, data=request.data)
        return Response({'card_id': str(card.card_id), 'status': card.status})


class MappingControlView(AuditedView):
    def post(self, request, mapping_id):
        from .lifecycle import control_mapping
        fields(request.data, ('action', 'reason'), ('action', 'reason'))
        mapping = control_mapping(user=request.user, mapping_id=mapping_id, **request.data)
        return Response({'mapping_id': mapping.pk, 'paused': mapping.paused})


class MappingReviewView(AuditedView):
    def post(self, request, mapping_id):
        from .lifecycle import review_mapping
        fields(request.data, ('review_ref',), ('review_ref',))
        mapping = review_mapping(user=request.user, mapping_id=mapping_id, **request.data)
        return Response({'mapping_id': mapping.pk, 'review_hash': mapping.review_hash})


class EnvironmentApprovalView(AuditedView):
    def post(self, request, container_id):
        from rest_framework import serializers
        from .lifecycle import approve_environment
        allowed = ('evidence_ref', 'checks', 'limits', 'expires_at')
        fields(request.data, allowed, allowed)
        data = dict(request.data)
        data['expires_at'] = serializers.DateTimeField().run_validation(data['expires_at'])
        approval = approve_environment(user=request.user, container_id=container_id, **data)
        return Response({'approval_id': approval.pk, 'expires_at': approval.expires_at,
                         'scope': 'operator_attestation_not_automated_isolation_proof'})


class AssignmentControlView(AuditedView):
    def post(self, request, assignment_id):
        from .lifecycle import control_assignment
        fields(request.data, ('action', 'reason'), ('action', 'reason'))
        services.owned_assignment(request.user, assignment_id)
        assignment = control_assignment(user=request.user, assignment_id=assignment_id, **request.data)
        return Response(assignment_payload(assignment))


class MappingListView(AuditedView):
    def get(self, request):
        return Response({'aup': AUP, 'aup_version': AUP_VERSION, 'mappings': [
            {'id': mapping.pk, 'task_id': mapping.task_id, 'repair_task_id': mapping.repair_task_id,
             'title': mapping.task.title, 'task_version': mapping.task.version,
             'claim_endpoint': f'/api/learning-map/tasks/{mapping.task_id}/claim/',
             'reviewed': bool(mapping.reviewed_at), 'paused': mapping.paused}
            for mapping in ChallengeMapping.objects.select_related('task').all()
        ]})


class AllocateView(AuditedView):
    def post(self, request, mapping_id):
        from rest_framework import serializers
        class Input(serializers.Serializer):
            attempt_id = serializers.UUIDField()
            accepted_aup = serializers.CharField()
        fields(request.data, ('attempt_id', 'accepted_aup'), ('attempt_id', 'accepted_aup'))
        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        get_object_or_404(ChallengeMapping, pk=mapping_id)
        assignment, created = services.allocate(student=request.user, mapping_id=mapping_id, **data.validated_data)
        return Response(assignment_payload(assignment), status=201 if created else 200)


class AssignmentListView(AuditedView):
    def get(self, request):
        from .lifecycle import expire_due
        expire_due(student=None if services.is_teacher(request.user) else request.user)
        queryset = LabAssignment.objects.all()
        if not services.is_teacher(request.user):
            queryset = queryset.filter(attempt__student=request.user)
        return Response([assignment_payload(item) for item in queryset])


class AssignmentView(AuditedView):
    def get(self, request, assignment_id):
        return Response(assignment_payload(services.owned_assignment(request.user, assignment_id)))


class HintRequestView(AuditedView):
    def post(self, request, assignment_id):
        fields(request.data, ('level',), ('level',))
        assignment = services.owned_assignment(request.user, assignment_id, write=True)
        record = services.hint_request(assignment=assignment, level=request.data['level'])
        return Response({'record_id': str(record.record_id), 'shown': record.shown}, status=201)


class HintDisplayView(AuditedView):
    def post(self, request, assignment_id, record_id):
        fields(request.data, ())
        assignment = services.owned_assignment(request.user, assignment_id, write=True)
        return Response(services.hint_display(assignment=assignment, record_id=record_id))
