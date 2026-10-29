from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from audit.models import AuditEvent
from challenges.models import ChallengeContainer
from learning_map.models import TaskAttempt
from learning_map.services.events import emit_event
from skill_review.models import AssistanceRecord
from skill_review.services.submissions import payload_hash, show_hint

from .models import ChallengeMapping, LabAssignment
from .policy import AUP, AUP_VERSION, approved_endpoint, configured_policy


CHALLENGE_VERIFIER = 'm5-juice-confidential-v1'
REPAIR_VERIFIER = 'm5-document-policy-v1'


def is_teacher(user):
    return user.is_staff or getattr(user, 'role', '') in ('teacher', 'admin')


def audit(user, action, assignment=None, **detail):
    return AuditEvent.objects.create(
        user=user, category='container', summary=f'Module5: {action}',
        level='WARNING' if action == 'denied' else 'INFO',
        detail={'source': 'practical_training', 'action': action,
                'assignment_id': str(assignment.assignment_id) if assignment else '', **detail},
    )


def owned_assignment(user, assignment_id, *, write=False):
    assignment = LabAssignment.objects.select_related(
        'attempt__task', 'attempt__student', 'attempt__catalog',
        'mapping__task', 'mapping__repair_task', 'container__challenge',
    ).filter(assignment_id=assignment_id).first()
    if not assignment or (assignment.attempt.student_id != user.id and (write or not is_teacher(user))):
        audit(user, 'denied', reason='assignment_access')
        raise NotFound()
    if assignment.expires_at <= timezone.now():
        from .lifecycle import expire_assignment
        expire_assignment(assignment.pk)
        assignment.refresh_from_db()
    return assignment


def task_snapshot(task):
    return {
        'task_id': task.pk, 'task_version': task.version, 'catalog_id': task.catalog_id,
        'challenge_id': task.challenge_id, 'title': task.title,
        'objectives': list(task.capabilities.order_by('stable_id').values('stable_id', 'observable_objective')),
        'knowledge_point_ids': sorted(set(task.capabilities.values_list('knowledge_points__stable_id', flat=True)) - {None}),
        'capability_ids': sorted(task.capabilities.values_list('stable_id', flat=True)),
        'prerequisite_ids': sorted(task.prerequisite_capabilities.values_list('stable_id', flat=True)),
        'materials': task.materials, 'hints': task.hints, 'acceptance': task.acceptance,
        'validator': task.validator, 'retest_task_keys': task.retest_task_keys,
    }


def mapping_hash(mapping):
    return payload_hash({'task': task_snapshot(mapping.task), 'repair_task': task_snapshot(mapping.repair_task),
                         'challenge_key': mapping.challenge_key})


def validate_mapping(mapping, *, allow_paused=False):
    task, repair = mapping.task, mapping.repair_task
    if (mapping.paused and not allow_paused) or not mapping.reviewed_by_id or not mapping.reviewed_at or not mapping.review_ref:
        raise ValidationError('映射未审核或已暂停。')
    if mapping.review_hash != mapping_hash(mapping):
        raise ValidationError('课程内容与审核快照不符，请重新审核。')
    if mapping.challenge_key != 'directoryListingChallenge':
        raise ValidationError('首期仅支持机密文档挑战。')
    for item, version in ((task, CHALLENGE_VERIFIER), (repair, REPAIR_VERIFIER)):
        if (not item.is_recommendable or item.catalog.status != 'published'
                or not item.has_required_parts or item.validator != {'type': 'server_verifier', 'version': version}):
            raise ValidationError('任务未开放或验证器契约不匹配。')
        if not item.capabilities.exists():
            raise ValidationError('任务缺少能力映射。')
    if task.capabilities.filter(dimension='repair').exists():
        raise ValidationError('挑战通过不能顺带授予修复能力；修复能力须绑定独立复核任务。')
    if (not task.challenge_id or task.challenge.docker_image != settings.JUICE_SHOP_IMAGE
            or repair.catalog_id != task.catalog_id or repair.task_key == task.task_key
            or repair.purpose != 'retest' or task.retest_task_keys != [repair.task_key]
            or not task.capabilities.filter(pk__in=repair.capabilities.all()).exists()):
        raise ValidationError('挑战与新场景修复题池绑定不一致。')


def active_assignment(assignment):
    mapping = ChallengeMapping.objects.select_for_update().get(pk=assignment.mapping_id)
    validate_mapping(mapping)
    if assignment.state not in ('allocated', 'active') or assignment.expires_at <= timezone.now():
        raise ValidationError('授权已暂停、隔离、重置或到期。')
    if (assignment.task_snapshot != task_snapshot(assignment.attempt.task)
            or assignment.attempt.task_version != assignment.attempt.task.version
            or assignment.container.container_id != assignment.scope['container_id']
            or assignment.container.port != assignment.scope['port']
            or assignment.container.user_id != assignment.attempt.student_id
            or assignment.container.challenge_id != assignment.attempt.task.challenge_id):
        raise ValidationError('任务或环境来源绑定已变化，请重新分配。')
    endpoint = approved_endpoint(assignment.container)
    if endpoint != assignment.scope['verifier_endpoint']:
        raise ValidationError('环境目标已变化。')
    return assignment


@transaction.atomic
def allocate(*, student, mapping_id, attempt_id, accepted_aup):
    if accepted_aup != AUP_VERSION:
        raise ValidationError('须确认当前可接受使用声明。')
    get_user_model().objects.select_for_update().get(pk=student.pk)
    mapping = ChallengeMapping.objects.select_for_update().get(pk=mapping_id)
    validate_mapping(mapping)
    attempt = TaskAttempt.objects.select_for_update().filter(attempt_id=attempt_id, student=student).first()
    if not attempt:
        raise NotFound()
    if (attempt.task_id != mapping.task_id or attempt.task_version != mapping.task.version
            or attempt.catalog_id != mapping.task.catalog_id
            or attempt.capability_ids != sorted(mapping.task.capabilities.values_list('stable_id', flat=True))
            or attempt.status not in ('claimed', 'in_progress')):
        raise ValidationError('先通过模块一领取本版本任务。')
    existing = LabAssignment.objects.filter(attempt=attempt).first()
    if existing:
        return active_assignment(existing), False
    policy = configured_policy()
    from .lifecycle import reconcile_cleanup
    reconcile_cleanup(student=student)
    count = LabAssignment.objects.filter(attempt__student=student).filter(
        Q(state__in=['allocated', 'active', 'paused', 'isolated'])
        | Q(physical_cleanup='pending_operator')
    ).count()
    if count >= policy['max_active_per_student']:
        raise ValidationError('已达到个人实训分配额度。')
    container = ChallengeContainer.objects.filter(
        user=student, challenge=mapping.task.challenge, status='running',
        labassignment__isnull=True,
    ).order_by('-created_at').first()
    if not container:
        raise ValidationError('请教师准备已验收且未使用的个人环境。')
    endpoint = approved_endpoint(container)
    now = timezone.now()
    expiry = min(now + timedelta(seconds=policy['duration_seconds']), container.expires_at,
                 container.environmentapproval.expires_at)
    assignment = LabAssignment.objects.create(
        mapping=mapping, attempt=attempt, container=container, task_snapshot=task_snapshot(mapping.task),
        policy=policy, expires_at=expiry,
        scope={'target': container.access_url, 'port': container.port, 'protocol': 'tcp',
               'verifier_endpoint': endpoint, 'container_id': container.container_id,
               'allowed_actions': ['read_challenge', 'discover_exposed_document', 'submit_policy_proposal'],
               'starts_at': now.isoformat(), 'ends_at': expiry.isoformat(),
               'aup_version': AUP_VERSION, 'aup': AUP,
               'repair_task_hash': payload_hash(task_snapshot(mapping.repair_task))},
    )
    audit(student, 'allocated', assignment, policy_version=policy['version'])
    return assignment, True


@transaction.atomic
def hint_request(*, assignment, level):
    assignment = LabAssignment.objects.select_for_update().get(pk=assignment.pk)
    active_assignment(assignment)
    if assignment.attempt.status not in ('claimed', 'in_progress'):
        raise ValidationError('已核验尝试请使用复盘入口。')
    if type(level) is not int or level not in (1, 2, 3, 4):
        raise ValidationError('提示级别须为 1–4。')
    cards = {card['level']: card for card in assignment.attempt.task.hints}
    if not cards.get(level, {}).get('content'):
        raise ValidationError('该提示未准备好。')
    attempt = assignment.attempt
    record = AssistanceRecord.objects.create(
        event_id=f'm5-hint-{uuid4().hex}', student=attempt.student, attempt=attempt, task=attempt.task,
        capability=attempt.task.capabilities.order_by('course_order', 'stable_id').first(),
        kind='hint', level=level, source='card', requested_at=timezone.now(), shown=False,
        content_ref=f'm5-card:{attempt.task_id}:{level}', created_by=attempt.student,
    )
    emit_event(user=attempt.student, event_type='hint_request', event_id=record.event_id,
               catalog=attempt.catalog, task=attempt.task, attempt_id=attempt.attempt_id,
               capability_ids=attempt.capability_ids, assistance_level=level, assistance_source='card',
               knowledge_point_ids=assignment.task_snapshot['knowledge_point_ids'],
               extra={'source': 'practical_training', 'shown': False})
    return record


@transaction.atomic
def hint_display(*, assignment, record_id):
    from skill_review.models import AssistanceRecord
    assignment = LabAssignment.objects.select_for_update().get(pk=assignment.pk)
    active_assignment(assignment)
    if assignment.attempt.status not in ('claimed', 'in_progress'):
        raise ValidationError('已核验尝试请使用复盘入口。')
    record = AssistanceRecord.objects.filter(record_id=record_id, attempt=assignment.attempt, source='card').first()
    if not record:
        raise NotFound()
    card = next((card for card in assignment.attempt.task.hints if card['level'] == record.level), None)
    if not card or not card.get('content'):
        raise ValidationError('材料已撤回。')
    show_hint(record=record, actor=assignment.attempt.student)
    return {'level': record.level, 'content': card['content'], 'source': 'card'}
