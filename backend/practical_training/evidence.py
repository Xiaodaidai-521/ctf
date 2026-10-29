from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from learning_map.models import TaskAttempt
from skill_review.services.submissions import payload_hash

from . import handoff, verifiers
from .models import LabAssignment, ServerEvidence
from .services import CHALLENGE_VERIFIER, active_assignment, audit


def valid_key(key):
    if not isinstance(key, str) or not key.strip() or len(key) > 64:
        raise ValidationError('幂等键应为非空字符串，最多 64 字符。')
    return key


def request_digest(assignment, attempt, kind, payload=None):
    return payload_hash({'assignment_id': str(assignment.assignment_id), 'attempt_id': str(attempt.attempt_id),
                         'kind': kind, 'payload': payload or {}})


def existing_evidence(key, digest):
    existing = ServerEvidence.objects.filter(key=key).select_related('result').first()
    if existing and existing.request_hash != digest:
        raise ValidationError('同键异内容或来源，拒绝复用证据。')
    return existing


@transaction.atomic
def persist_evidence(*, assignment, attempt, key, request_hash, source, observation, version, status, error=''):
    content_hash = payload_hash({'source': source, 'observation': observation,
                                 'version': version, 'status': status, 'error': error})
    existing = existing_evidence(key, request_hash)
    if existing:
        if existing.content_hash != content_hash:
            raise ValidationError('同键异内容证据被拒绝。')
        return existing
    if (source.get('attempt_id') != str(attempt.attempt_id)
            or source.get('assignment_id') != str(assignment.assignment_id)
            or source.get('task_version') != attempt.task_version
            or source.get('student_id') != attempt.student_id):
        raise ValidationError('证据来源绑定不一致。')
    row = ServerEvidence.objects.create(
        assignment=assignment, attempt=attempt, key=key, request_hash=request_hash,
        source=source, observation=observation, content_hash=content_hash,
        verifier_version=version, status=status, error=error,
    )
    handoff.deliver(row)
    return row


def source_binding(assignment, attempt, kind):
    return {'kind': kind, 'assignment_id': str(assignment.assignment_id),
            'attempt_id': str(attempt.attempt_id), 'student_id': attempt.student_id,
            'task_id': attempt.task_id, 'task_version': attempt.task_version,
            'catalog_version': attempt.catalog.version,
            'container_id': assignment.container.container_id,
            'challenge_id': assignment.mapping.task.challenge_id,
            'challenge_key': assignment.mapping.challenge_key}


@transaction.atomic
def start(assignment):
    assignment = LabAssignment.objects.select_for_update().get(pk=assignment.pk)
    active_assignment(assignment)
    if assignment.baseline_observed_at:
        return assignment
    if assignment.attempt.status not in ('claimed', 'in_progress'):
        raise ValidationError('该尝试已提交或放弃。')
    try:
        observation = verifiers.observe_challenge(assignment.scope['verifier_endpoint'], assignment.mapping.challenge_key)
    except verifiers.VerifierUnavailable as exc:
        audit(assignment.attempt.student, 'baseline_unavailable', assignment, error=str(exc))
        return None
    if observation['solved']:
        raise ValidationError('实例已有完成状态，须使用全新环境；不能归因给当前尝试。')
    assignment.baseline_observed_at = timezone.now()
    assignment.state = 'active'
    assignment.save(update_fields=['baseline_observed_at', 'state'])
    assignment.attempt.status = 'in_progress'
    assignment.attempt.save(update_fields=['status'])
    from learning_map.services.events import emit_event
    emit_event(user=assignment.attempt.student, event_type='task_start',
               event_id=f'm5-start-{assignment.assignment_id}', task=assignment.attempt.task,
               catalog=assignment.attempt.catalog, attempt_id=assignment.attempt.attempt_id,
               capability_ids=assignment.attempt.capability_ids,
               extra={'source': 'practical_training', 'baseline_solved': False})
    return assignment


@transaction.atomic
def verify_challenge(*, assignment, key):
    valid_key(key)
    assignment = LabAssignment.objects.select_for_update().get(pk=assignment.pk)
    attempt = TaskAttempt.objects.select_for_update().get(pk=assignment.attempt_id)
    digest = request_digest(assignment, attempt, 'challenge')
    existing = existing_evidence(key, digest)
    if existing:
        return existing, False
    active_assignment(assignment)
    if not assignment.baseline_observed_at or assignment.state != 'active':
        raise ValidationError('尚未开始并记录干净基线。')
    if attempt.status not in ('claimed', 'in_progress') or attempt.submissions.exists():
        raise ValidationError('尝试已提交，请为重试领取新尝试和环境。')
    error = ''
    try:
        observation = verifiers.observe_challenge(assignment.scope['verifier_endpoint'], assignment.mapping.challenge_key)
        status = 'passed' if observation['solved'] else 'failed'
    except verifiers.VerifierUnavailable as exc:
        observation, status, error = {}, 'error', str(exc)
    source = source_binding(assignment, attempt, 'juice_shop_state')
    source['baseline_observed_at'] = assignment.baseline_observed_at.isoformat()
    row = persist_evidence(assignment=assignment, attempt=attempt, key=key, request_hash=digest,
                           source=source, observation=observation, version=CHALLENGE_VERIFIER, status=status, error=error)
    if row.status == 'passed':
        from skill_review.services.retest import schedule_retest
        schedule_retest(row.result.submission, due_days=0)
    return row, True
