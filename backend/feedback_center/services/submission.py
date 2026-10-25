"""Feedback submission, link resolution, dedup and student evidence updates."""

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from learning_map.models import (
    Capability,
    CatalogVersion,
    KnowledgePoint,
    TaskAttempt,
    TaskPackage,
)

from .. import constants
from ..models import FeedbackRelation, FeedbackTicket
from . import evidence as evidence_service
from .audit import now, record_action, role_of
from .events import sync_links
from .module6 import collect_attempt_context


User = get_user_model()


class FeedbackError(Exception):
    def __init__(self, detail, *, code='invalid_request', status_code=400, extra=None):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status_code = status_code
        self.extra = extra or {}


class IdempotencyConflict(FeedbackError):
    def __init__(self, detail='相同提交标识对应不同内容，拒绝覆盖；请使用新的提交标识。'):
        super().__init__(detail, code='idempotency_conflict', status_code=409)


class ExecutionNotOpen(FeedbackError):
    def __init__(self):
        super().__init__(
            '执行反馈入口尚未开放，等待独立里程碑 I 通过。首期只接收识别、决策和教学反馈。',
            code='milestone_i_not_open',
            status_code=409,
            extra={'milestone_i_open': False, 'execution_feedback_open': False},
        )


@dataclass
class SubmissionResult:
    ticket: FeedbackTicket
    created: bool
    idempotent: bool
    links: list
    event_sync: dict


def _is_teacher(user):
    return bool(
        getattr(user, 'is_authenticated', False)
        and (getattr(user, 'is_teacher', False) or getattr(user, 'is_admin', False) or user.is_superuser)
    )


def _resolve_student(actor, data):
    if not _is_teacher(actor):
        requested = data.get('student')
        if requested and int(requested) != actor.id:
            raise FeedbackError('学生只能提交本人反馈。', code='forbidden', status_code=403)
        return actor
    student_id = data.get('student') or actor.id
    student = User.objects.filter(pk=student_id).first()
    if not student:
        raise FeedbackError('反馈所属学生不存在。', code='student_not_found', status_code=404)
    return student


def _resolve_links(actor, data):
    student = _resolve_student(actor, data)
    attempt = None
    catalog = None
    task = None
    capability = None
    knowledge_point = None

    if data.get('attempt_id'):
        attempt = TaskAttempt.objects.select_related('task', 'catalog', 'student').filter(
            attempt_id=data['attempt_id'],
        ).first()
        if not attempt:
            raise FeedbackError('任务尝试不存在。', code='attempt_not_found', status_code=404)
        if attempt.student_id != student.id:
            raise FeedbackError('任务尝试不属于该学生。', code='attempt_owner_mismatch', status_code=403)
        catalog = attempt.catalog
        task = attempt.task

    if data.get('catalog_version'):
        requested_catalog = CatalogVersion.objects.filter(version=data['catalog_version']).first()
        if not requested_catalog:
            raise FeedbackError('目录版本不存在。', code='catalog_not_found', status_code=404)
        if catalog and catalog.pk != requested_catalog.pk:
            raise FeedbackError('目录版本与任务尝试不一致。', code='catalog_mismatch')
        catalog = requested_catalog

    if data.get('task_key'):
        if not data.get('task_version'):
            raise FeedbackError('按任务键提交时必须同时提供任务版本。', code='task_version_required')
        requested_task = TaskPackage.objects.filter(
            task_key=data['task_key'], version=data['task_version'],
        ).select_related('catalog').first()
        if not requested_task:
            raise FeedbackError('任务版本不存在。', code='task_not_found', status_code=404)
        if catalog and requested_task.catalog_id != catalog.pk:
            raise FeedbackError('任务与目录版本不一致。', code='task_catalog_mismatch')
        if task and task.pk != requested_task.pk:
            raise FeedbackError('任务与尝试快照不一致。', code='task_attempt_mismatch')
        task = requested_task
        catalog = task.catalog

    task_version = (
        data.get('task_version')
        or (attempt.task_version if attempt else '')
        or (task.version if task else '')
    )

    capability_id = data.get('capability_id')
    if capability_id:
        if not catalog:
            raise FeedbackError('提供能力 ID 时必须同时提供目录版本。', code='catalog_required')
        capability = Capability.objects.filter(catalog=catalog, stable_id=capability_id).first()
        if not capability:
            raise FeedbackError('能力不在指定目录版本中。', code='capability_not_found', status_code=404)
        if attempt and capability_id not in (attempt.capability_ids or []):
            raise FeedbackError('能力不在该尝试的能力快照中。', code='capability_attempt_mismatch')
    elif attempt and catalog and len(attempt.capability_ids or []) == 1:
        capability = Capability.objects.filter(
            catalog=catalog, stable_id=attempt.capability_ids[0],
        ).first()

    knowledge_point_id = data.get('knowledge_point_id')
    if knowledge_point_id:
        if not catalog:
            raise FeedbackError('提供知识点 ID 时必须同时提供目录版本。', code='catalog_required')
        knowledge_point = KnowledgePoint.objects.filter(
            catalog=catalog, stable_id=knowledge_point_id,
        ).first()
        if not knowledge_point:
            raise FeedbackError('知识点不在指定目录版本中。', code='knowledge_point_not_found', status_code=404)
        if capability and not capability.knowledge_points.filter(pk=knowledge_point.pk).exists():
            raise FeedbackError('知识点不属于所选能力。', code='knowledge_point_mismatch')
    elif capability:
        points = list(capability.knowledge_points.all()[:2])
        if len(points) == 1:
            knowledge_point = points[0]

    attempt_ref = str(attempt.attempt_id) if attempt else str(data.get('attempt_ref') or '')
    return {
        'student': student,
        'attempt': attempt,
        'catalog': catalog,
        'task': task,
        'task_version': task_version,
        'attempt_ref': attempt_ref,
        'capability': capability,
        'knowledge_point': knowledge_point,
    }


def _context_snapshot(links, data, module6_context):
    task = links['task']
    attempt = links['attempt']
    capability = links['capability']
    knowledge_point = links['knowledge_point']
    catalog = links['catalog']
    return {
        'schema_version': constants.FEEDBACK_SCHEMA_VERSION,
        'catalog_version': catalog.version if catalog else '',
        'task': {
            'task_key': task.task_key if task else '',
            'version': task.version if task else '',
            'title': task.title if task else '',
            'status': task.status if task else '',
            'purpose': task.purpose if task else '',
            'execution_mode': task.execution_mode if task else '',
            'requires_milestone_i': bool(task.requires_milestone_i) if task else False,
            'environment_available': bool(task.environment_available) if task else None,
            'materials_withdrawn': bool(task.materials_withdrawn) if task else None,
        },
        'attempt': {
            'attempt_id': str(attempt.attempt_id) if attempt else '',
            'status': attempt.status if attempt else '',
            'claimed_at': attempt.claimed_at.isoformat() if attempt else None,
            'submitted_at': attempt.submitted_at.isoformat() if attempt and attempt.submitted_at else None,
            'evidence_ref': attempt.evidence_ref if attempt else '',
            'capability_ids': list(attempt.capability_ids or []) if attempt else [],
        },
        'capability_id': capability.stable_id if capability else '',
        'knowledge_point_id': knowledge_point.stable_id if knowledge_point else '',
        'original_decision': {
            'ref': data.get('original_decision_ref') or '',
            'version': data.get('original_decision_version') or '',
            'snapshot': data.get('original_decision_snapshot') or {},
        },
        'module6': module6_context,
        'note': '只读引用快照；未创建或覆盖任何学习事实、成绩、提示或复测记录。',
    }


def _request_payload(links, data, student):
    task = links['task']
    catalog = links['catalog']
    capability = links['capability']
    knowledge_point = links['knowledge_point']
    attempt = links['attempt']
    return {
        'student': student.id,
        'category': data['category'],
        'issue_type': data['issue_type'],
        'catalog_version': catalog.version if catalog else (data.get('catalog_version') or ''),
        'task_key': task.task_key if task else (data.get('task_key') or ''),
        'task_version': links['task_version'],
        'attempt_id': str(attempt.attempt_id) if attempt else '',
        'attempt_ref': links['attempt_ref'],
        'capability_id': capability.stable_id if capability else (data.get('capability_id') or ''),
        'knowledge_point_id': knowledge_point.stable_id if knowledge_point else (data.get('knowledge_point_id') or ''),
        'dispute': str(data.get('dispute') or '').strip(),
        'expected_result': str(data.get('expected_result') or '').strip(),
        'reason': str(data.get('reason') or '').strip(),
        'original_decision_ref': str(data.get('original_decision_ref') or '').strip(),
        'original_decision_version': str(data.get('original_decision_version') or '').strip(),
        'original_decision_snapshot': data.get('original_decision_snapshot') or {},
        'involves_actual_execution': bool(data.get('involves_actual_execution')),
        'technical_issue': bool(data.get('technical_issue')),
        'evidence': evidence_service.normalize_evidence_inputs(data.get('evidence') or []),
    }


def _original_from_evidence(data):
    for item in data.get('evidence') or []:
        if item.get('slot') == constants.EVIDENCE_SLOT_ORIGINAL_DECISION:
            return (
                str(item.get('ref') or '').strip(),
                str(item.get('version') or '').strip(),
            )
    return ('', '')


def _validate_category_issue(category, issue_type):
    if category not in dict(constants.CATEGORY_CHOICES):
        raise FeedbackError('未知反馈类别。', code='invalid_category')
    if issue_type not in {value for value, _ in constants.issue_type_choices(category)}:
        raise FeedbackError('问题类型与反馈类别不匹配。', code='invalid_issue_type')


def _existing_submission(actor, client_request_id, fingerprint):
    existing = FeedbackTicket.objects.select_for_update().select_related(
        'catalog', 'task', 'attempt', 'capability', 'knowledge_point', 'duplicate_of',
    ).filter(submitter=actor, client_request_id=client_request_id).first()
    if not existing:
        return None
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyConflict()
    return existing


@transaction.atomic
def create_feedback(actor, data):
    _validate_category_issue(data['category'], data['issue_type'])
    if data.get('involves_actual_execution') and not constants.EXECUTION_FEEDBACK_OPEN:
        raise ExecutionNotOpen()
    if not str(data.get('client_request_id') or '').strip():
        raise FeedbackError('缺少客户端提交标识。', code='client_request_id_required')
    if not str(data.get('dispute') or '').strip():
        raise FeedbackError('请填写具体争议。', code='dispute_required')

    links = _resolve_links(actor, data)
    student = links['student']
    module6_context = collect_attempt_context(links['attempt'])
    fingerprint = evidence_service.compute_request_fingerprint(_request_payload(links, data, student))

    existing = _existing_submission(actor, data['client_request_id'], fingerprint)
    if existing is not None:
        links_to_sync = list(existing.event_links.filter(status=constants.EVENT_LINK_PENDING))
        return SubmissionResult(
            ticket=existing, created=False, idempotent=True,
            links=links_to_sync, event_sync=sync_links(links_to_sync),
        )

    original_ref = str(data.get('original_decision_ref') or '').strip()
    original_version = str(data.get('original_decision_version') or '').strip()
    if not original_ref:
        original_ref, evidence_version = _original_from_evidence(data)
        original_version = original_version or evidence_version

    task = links['task']
    attempt = links['attempt']
    catalog = links['catalog']
    capability = links['capability']
    knowledge_point = links['knowledge_point']
    dedup_key = evidence_service.compute_dedup_key(
        student_id=student.id,
        attempt_key=links['attempt_ref'],
        task_key=task.task_key if task else '',
        task_version=links['task_version'],
        category=data['category'],
        dispute=data['dispute'],
    )

    ticket_fields = {
        'client_request_id': str(data['client_request_id']).strip(),
        'request_fingerprint': fingerprint,
        'submitter': actor,
        'submitter_role': role_of(actor),
        'student': student,
        'catalog': catalog,
        'task': task,
        'task_version': links['task_version'],
        'attempt': attempt,
        'attempt_ref': links['attempt_ref'],
        'capability': capability,
        'knowledge_point': knowledge_point,
        'category': data['category'],
        'issue_type': data['issue_type'],
        'dispute': str(data['dispute']).strip(),
        'expected_result': str(data.get('expected_result') or '').strip(),
        'reason': str(data.get('reason') or '').strip(),
        'original_decision_ref': original_ref,
        'original_decision_version': original_version,
        'original_decision_snapshot': data.get('original_decision_snapshot') or {},
        'context_snapshot': _context_snapshot(links, data, module6_context),
        'involves_actual_execution': False,
        'technical_issue': bool(data.get('technical_issue')),
        'status': constants.STATUS_SUBMITTED,
        'version': 1,
        'dedup_key': dedup_key,
        'owner_role': constants.default_owner_role(data['category'], data['issue_type']),
        'handling_destination': constants.default_destination(data['category'], data['issue_type']),
        'effect_status': constants.EFFECT_NOT_ASSESSED,
        'submitted_at': now(),
    }

    try:
        with transaction.atomic():
            ticket = FeedbackTicket.objects.create(**ticket_fields)
    except IntegrityError:
        existing = _existing_submission(actor, data['client_request_id'], fingerprint)
        if existing is not None:
            links_to_sync = list(existing.event_links.filter(status=constants.EVENT_LINK_PENDING))
            return SubmissionResult(
                ticket=existing, created=False, idempotent=True,
                links=links_to_sync, event_sync=sync_links(links_to_sync),
            )
        raise

    evidence_service.create_initial_evidence(
        ticket, data.get('evidence') or [], actor=actor, context=module6_context,
    )

    _, submit_link = record_action(
        ticket, action='submit', actor=actor, from_status='',
        to_status=constants.STATUS_SUBMITTED,
        reason='学生或教师提交反馈；服务端落库后返回成功。',
        metadata={'schema_version': constants.FEEDBACK_SCHEMA_VERSION},
        event_type=constants.EVENT_FEEDBACK_SUBMITTED,
    )

    # Dedup is a server-side state transition.  It never merges two records:
    # the duplicate keeps its own text, source and main-record reference.
    ticket.status = constants.STATUS_DEDUPLICATING
    ticket.version = 2
    ticket.save(update_fields=['status', 'version', 'updated_at'])

    main = FeedbackTicket.objects.select_for_update().filter(
        dedup_key=dedup_key, duplicate_of__isnull=True,
    ).exclude(pk=ticket.pk).order_by('created_at').first()

    if main is not None:
        ticket.duplicate_of = main
        ticket.status = constants.STATUS_DUPLICATE
        relation_note = '同尝试、同类别、同争议的重复提交；保留原文并关联主记录。'
        FeedbackRelation.objects.get_or_create(
            from_ticket=main, to_ticket=ticket, relation_type='duplicate',
            defaults={'created_by': actor, 'note': relation_note},
        )
        dedup_metadata = {
            'duplicate_of': str(main.feedback_id),
            'reason': 'same_attempt_same_category_same_dispute',
            'note': '重复投诉不增加独立证据。',
        }
    else:
        ticket.status = (
            constants.STATUS_PENDING_EVIDENCE
            if ticket.missing_evidence else constants.STATUS_PENDING_FACT_REVIEW
        )
        dedup_metadata = {
            'duplicate_of': '',
            'missing_evidence': list(ticket.missing_evidence or []),
            'reason': 'no_exact_duplicate',
        }
    ticket.deduplicated_at = now()
    ticket.save(update_fields=[
        'duplicate_of', 'status', 'deduplicated_at', 'version', 'updated_at',
    ])

    # Same attempt, different category: keep both conclusions and record the
    # relation.  A duplicate is not used as an independent instance.
    if attempt is not None:
        others = FeedbackTicket.objects.select_for_update().filter(
            attempt=attempt,
        ).exclude(pk=ticket.pk).exclude(duplicate_of__isnull=False)
        for other in others:
            if other.category != ticket.category:
                FeedbackRelation.objects.get_or_create(
                    from_ticket=other, to_ticket=ticket,
                    relation_type='same_attempt_cross_category',
                    defaults={
                        'created_by': actor,
                        'note': '同一尝试的跨类别反馈；分别保留结论、责任人和处理去向。',
                    },
                )

    _, dedup_link = record_action(
        ticket, action='dedup', actor=None,
        from_status=constants.STATUS_DEDUPLICATING, to_status=ticket.status,
        reason='按客户端提交标识去重，并核对同尝试/同类别/同争议重复。',
        metadata=dedup_metadata,
        event_type=constants.EVENT_FEEDBACK_DEDUPLICATED,
    )

    links_to_sync = [link for link in (submit_link, dedup_link) if link is not None]
    return SubmissionResult(
        ticket=ticket, created=True, idempotent=False,
        links=links_to_sync, event_sync=sync_links(links_to_sync),
    )


@transaction.atomic
def add_student_evidence(actor, ticket, items, reason=''):
    """Append evidence and move the ticket back into review.

    A duplicate record cannot accumulate evidence; the main record is the
    single place to continue.  The main record ID is returned so the student or
    teacher can open it.
    """

    is_teacher = _is_teacher(actor)
    if not is_teacher and actor.id not in (ticket.student_id, ticket.submitter_id):
        raise FeedbackError('只能为本人反馈补充证据。', code='forbidden', status_code=403)
    if ticket.status == constants.STATUS_DUPLICATE:
        raise FeedbackError(
            '该反馈已关联主记录，请在主记录中补充证据。',
            code='duplicate_record',
            status_code=409,
            extra={'duplicate_of': str(ticket.duplicate_of.feedback_id) if ticket.duplicate_of else ''},
        )
    if ticket.status in (constants.STATUS_SUBMITTED, constants.STATUS_DEDUPLICATING):
        raise FeedbackError('反馈尚未完成去重，暂不能补充证据。', code='not_ready', status_code=409)

    from_status = ticket.status
    changed = evidence_service.add_evidence(
        ticket, items, actor=actor,
        source=constants.EVIDENCE_SOURCE_TEACHER if is_teacher else constants.EVIDENCE_SOURCE_SUBMITTER,
        default_visibility=constants.VISIBILITY_STUDENT,
    )
    if not changed:
        raise FeedbackError('没有可保存的新证据。', code='evidence_required')

    if ticket.status == constants.STATUS_PENDING_EVIDENCE:
        to_status = constants.STATUS_PENDING_FACT_REVIEW
    elif ticket.status in constants.REOPENABLE_STATUSES or ticket.status == constants.STATUS_HANDLING:
        to_status = constants.STATUS_REOPENED
        ticket.reopened_at = now()
    else:
        to_status = ticket.status

    ticket.status = to_status
    ticket.version += 1
    ticket.save(update_fields=[
        'status', 'version', 'reopened_at', 'last_evidence_at', 'updated_at',
    ])

    _, link = record_action(
        ticket, action='provide_evidence', actor=actor,
        from_status=from_status, to_status=to_status,
        reason=reason or '补充证据；原提交与原始判定保留。',
        metadata={
            'slots': changed,
            'missing_evidence': list(ticket.missing_evidence or []),
            'reopened': to_status == constants.STATUS_REOPENED,
        },
        event_type=constants.EVENT_FEEDBACK_EVIDENCE_ADDED,
    )
    sync = sync_links([link] if link else [])
    return ticket, sync
