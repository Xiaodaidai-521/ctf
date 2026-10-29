"""Platform authorization lifecycle; never claims Docker/network destruction."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from challenges.models import ChallengeContainer
from .models import ChallengeMapping, EnvironmentApproval, LabAssignment
from .policy import REQUIRED_CHECKS, configured_policy, environment_binding, validate_resource_limits
from .services import audit, is_teacher, mapping_hash, validate_mapping


TERMINAL_STATES = ('reset', 'expired')


def require_teacher(user):
    if not is_teacher(user):
        raise PermissionDenied('仅教师或管理员可操作。')


def reason_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        raise ValidationError('须填写 1–255 字符的原因或证据引用。')
    return value.strip()


@transaction.atomic
def review_mapping(*, user, mapping_id, review_ref):
    require_teacher(user)
    mapping = ChallengeMapping.objects.select_for_update().filter(pk=mapping_id).first()
    if not mapping:
        raise NotFound()
    mapping.review_ref = reason_text(review_ref)
    mapping.reviewed_by = user
    mapping.reviewed_at = timezone.now()
    mapping.review_hash = mapping_hash(mapping)
    validate_mapping(mapping, allow_paused=True)
    mapping.save(update_fields=['review_ref', 'reviewed_by', 'reviewed_at', 'review_hash'])
    audit(user, 'mapping_reviewed', mapping_id=mapping.pk, review_ref=mapping.review_ref,
          review_hash=mapping.review_hash)
    return mapping


@transaction.atomic
def control_mapping(*, user, mapping_id, action, reason):
    require_teacher(user)
    reason = reason_text(reason)
    mapping = ChallengeMapping.objects.select_for_update().filter(pk=mapping_id).first()
    if not mapping:
        raise NotFound()
    if action not in ('pause', 'resume'):
        raise ValidationError('任务控制只接受 pause/resume。')
    mapping.paused = action == 'pause'
    if not mapping.paused:
        validate_mapping(mapping)
    mapping.save(update_fields=['paused'])
    audit(user, f'mapping_{action}', mapping_id=mapping.pk, reason=reason)
    return mapping


@transaction.atomic
def approve_environment(*, user, container_id, evidence_ref, checks, limits, expires_at):
    require_teacher(user)
    reference = reason_text(evidence_ref)
    container = ChallengeContainer.objects.select_for_update().filter(pk=container_id).first()
    if not container:
        raise NotFound()
    if LabAssignment.objects.filter(container=container).exists():
        raise ValidationError('已分配的环境不能换绑验收登记，须准备新环境。')
    if (not container.is_running or not container.expires_at or not container.started_at
            or expires_at <= timezone.now() or expires_at > container.expires_at):
        raise ValidationError('验收有效期须在运行实例的授权时段内。')
    if not isinstance(checks, dict) or set(checks) != set(REQUIRED_CHECKS) or any(value is not True for value in checks.values()):
        raise ValidationError('须逐项登记真实隔离验收，缺项不得放行。')
    validate_resource_limits(limits, configured_policy())
    approval, _ = EnvironmentApproval.objects.update_or_create(container=container, defaults={
        'reviewed_by': user, 'evidence_ref': reference, 'expires_at': expires_at, 'revoked': False,
        'checks': {**checks, 'limits': limits, 'binding': environment_binding(container)},
    })
    audit(user, 'environment_attested', container_pk=container.pk, evidence_ref=reference,
          binding=approval.checks['binding'], note='operator_attestation_not_automated_isolation_proof')
    return approval


def revoke_authorization(assignment, state):
    assignment.state = state
    assignment.physical_cleanup = 'pending_operator'
    assignment.save(update_fields=['state', 'physical_cleanup'])
    EnvironmentApproval.objects.filter(container=assignment.container).update(revoked=True)
    # Do not rewrite verified attempts, results or repair evidence.
    if state in TERMINAL_STATES and assignment.attempt.status in ('claimed', 'in_progress'):
        assignment.attempt.status = 'abandoned'
        assignment.attempt.save(update_fields=['status'])


@transaction.atomic
def control_assignment(*, user, assignment_id, action, reason):
    reason = reason_text(reason)
    assignment = LabAssignment.objects.select_for_update().filter(assignment_id=assignment_id).first()
    if not assignment or (not is_teacher(user) and assignment.attempt.student_id != user.pk):
        raise NotFound()
    if action != 'reset':
        require_teacher(user)
    if action not in ('pause', 'resume', 'isolate', 'reset'):
        raise ValidationError('不支持的生命周期动作。')
    if assignment.state in TERMINAL_STATES or assignment.expires_at <= timezone.now():
        raise ValidationError('授权已结束，不能恢复旧环境。')
    if action == 'pause' and assignment.state in ('allocated', 'active'):
        assignment.state = 'paused'
        assignment.save(update_fields=['state'])
    elif action == 'resume' and assignment.state == 'paused':
        assignment.state = 'active' if assignment.baseline_observed_at else 'allocated'
        from .services import active_assignment
        active_assignment(assignment)
        assignment.save(update_fields=['state'])
    elif action in ('isolate', 'reset'):
        revoke_authorization(assignment, 'isolated' if action == 'isolate' else 'reset')
    else:
        raise ValidationError('当前状态不允许该操作。')
    audit(user, f'assignment_{action}', assignment, reason=reason, state=assignment.state,
          physical_cleanup=assignment.physical_cleanup)
    return assignment


@transaction.atomic
def expire_assignment(assignment_id, now=None):
    now = now or timezone.now()
    assignment = LabAssignment.objects.select_for_update().get(pk=assignment_id)
    if assignment.state in TERMINAL_STATES or assignment.expires_at > now:
        return False
    revoke_authorization(assignment, 'expired')
    audit(None, 'assignment_expired', assignment, physical_cleanup=assignment.physical_cleanup)
    return True


@transaction.atomic
def reconcile_cleanup(*, student=None):
    queryset = LabAssignment.objects.select_for_update().filter(
        physical_cleanup='pending_operator', container__status__in=['stopped', 'destroyed'],
        container__destroyed_at__isnull=False, container__access_url='',
    )
    if student is not None:
        queryset = queryset.filter(attempt__student=student)
    count = 0
    for assignment in queryset:
        assignment.physical_cleanup = 'confirmed_by_runtime'
        assignment.save(update_fields=['physical_cleanup'])
        audit(None, 'cleanup_runtime_receipt', assignment, container_id=assignment.container.container_id)
        count += 1
    return count


def expire_due(*, student=None, now=None):
    now = now or timezone.now()
    queryset = LabAssignment.objects.filter(expires_at__lte=now).exclude(state__in=TERMINAL_STATES)
    if student is not None:
        queryset = queryset.filter(attempt__student=student)
    return sum(expire_assignment(pk, now) for pk in list(queryset.values_list('pk', flat=True)))
