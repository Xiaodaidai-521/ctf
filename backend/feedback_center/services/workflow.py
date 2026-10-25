"""Teacher workflow for module 7 phase 1.

Every handler re-fetches the ticket with ``select_for_update``, checks the
expected version and the role, and appends an action row.  A review correction
creates a new review; it never edits the previous conclusion.  A referral must
be acknowledged before the ticket can be marked handled.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from learning_map.models import VerificationFact

from .. import constants
from ..models import FeedbackReferral, FeedbackRelation, FeedbackReview, FeedbackTicket
from . import evidence as evidence_service
from .audit import create_review, now, record_action, role_of
from .events import sync_links


User = get_user_model()


class WorkflowError(Exception):
    def __init__(self, detail, *, code='invalid_transition', status_code=409, extra=None):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status_code = status_code
        self.extra = extra or {}


def _is_teacher(user):
    return bool(
        getattr(user, 'is_authenticated', False)
        and (getattr(user, 'is_teacher', False) or getattr(user, 'is_admin', False) or user.is_superuser)
    )


def _is_admin(user):
    return bool(
        getattr(user, 'is_authenticated', False)
        and (getattr(user, 'is_admin', False) or user.is_superuser)
    )


def _require_teacher(actor):
    if not _is_teacher(actor):
        raise WorkflowError('需要教师或管理员权限。', code='forbidden', status_code=403)


def _require_admin(actor):
    if not _is_admin(actor):
        raise WorkflowError('需要管理员权限。', code='forbidden', status_code=403)


def _locked(ticket):
    return FeedbackTicket.objects.select_for_update().select_related(
        'catalog', 'task', 'attempt', 'capability', 'knowledge_point',
        'duplicate_of', 'owner', 'handling_owner', 'current_review',
    ).get(pk=ticket.pk)


def _check_version(ticket, payload):
    expected = payload.get('expected_version')
    if expected is None:
        raise WorkflowError('缺少 expected_version，拒绝并发覆盖。', code='version_required')
    if int(expected) != ticket.version:
        raise WorkflowError(
            '工单已被其他操作更新，请刷新后重试。',
            code='version_conflict',
            status_code=409,
            extra={'current_version': ticket.version, 'status': ticket.status},
        )


def _require_reason(payload, code='reason_required'):
    reason = str(payload.get('reason') or '').strip()
    if not reason:
        raise WorkflowError('必须填写理由。', code=code)
    return reason


def _parse_dt(value):
    if value in (None, ''):
        return None
    if hasattr(value, 'isoformat'):
        parsed = value
    else:
        parsed = parse_datetime(str(value))
    if parsed is None:
        raise WorkflowError('时间格式必须为 ISO 8601。', code='invalid_datetime')
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _validate_destination(destination):
    if destination not in dict(constants.DESTINATION_CHOICES):
        raise WorkflowError('未知处理去向。', code='invalid_destination')
    if destination == constants.DESTINATION_EXECUTION:
        raise WorkflowError(
            '执行集成去向尚未开放，等待独立里程碑 I。',
            code='milestone_i_not_open',
            extra={'milestone_i_open': False},
        )
    return destination


def _required_destination(ticket):
    if ticket.issue_type == 'scoring_dispute':
        return constants.DESTINATION_MODULE6
    if ticket.issue_type == 'catalog_or_recommendation':
        return constants.DESTINATION_MODULE1
    if ticket.technical_issue:
        return constants.DESTINATION_PLATFORM
    return None


def _check_special_destination(ticket, destination):
    required = _required_destination(ticket)
    if required and destination != required:
        raise WorkflowError(
            f'该问题必须转交 {constants.DESTINATION_LABELS.get(required, required)}，不能直接按其他去向处理。',
            code='destination_required',
            extra={'required_destination': required},
        )


def _confirm_gates(ticket):
    if not ticket.evidence_complete:
        raise WorkflowError(
            '关键证据缺失，不能确认；请先补充证据或标记未知。',
            code='evidence_incomplete',
            extra={'missing_evidence': list(ticket.missing_evidence or [])},
        )
    if not ticket.mapping_complete:
        raise WorkflowError(
            '反馈缺少任务、尝试、版本或能力/知识点关联，不能确认进入候选依据。',
            code='mapping_incomplete',
            extra={'missing_mapping': evidence_service.mapping_missing_fields(ticket)},
        )


def _ensure_referral(ticket, *, destination, actor, note):
    existing = ticket.referrals.filter(destination=destination).exclude(
        status=constants.REFERRAL_DECLINED,
    ).first()
    if existing:
        return existing
    return FeedbackReferral.objects.create(
        ticket=ticket,
        destination=destination,
        note=note or '处理开始时登记转交，等待接收方确认。',
        status=constants.REFERRAL_PENDING,
        created_by=actor,
    )


def _claim(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status not in (
        constants.STATUS_PENDING_FACT_REVIEW,
        constants.STATUS_PENDING_EVIDENCE,
        constants.STATUS_REOPENED,
    ):
        raise WorkflowError('当前状态不能认领。', code='invalid_status')
    if ticket.owner_id and ticket.owner_id != actor.id and not _is_admin(actor):
        raise WorkflowError(
            '该工单已由其他责任人认领。',
            code='owner_conflict',
            extra={'owner_id': ticket.owner_id},
        )
    from_status = ticket.status
    to_status = constants.STATUS_PENDING_FACT_REVIEW if ticket.status == constants.STATUS_REOPENED else ticket.status
    ticket.owner = actor
    ticket.owner_role = payload.get('owner_role') or ticket.owner_role
    ticket.assigned_at = now()
    ticket.status = to_status
    ticket.version += 1
    ticket.save(update_fields=[
        'owner', 'owner_role', 'assigned_at', 'status', 'version', 'updated_at',
    ])
    action, link = record_action(
        ticket, action='claim', actor=actor,
        from_status=from_status, to_status=to_status,
        reason=payload.get('reason') or '负责人认领。',
        metadata={'owner_role': ticket.owner_role},
        event_type=(
            constants.EVENT_FEEDBACK_STATUS_CHANGED
            if from_status != to_status else ''
        ),
    )
    return ticket, action, link


def _assign(actor, ticket, payload):
    _require_admin(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    owner_id = payload.get('owner_id')
    owner = User.objects.filter(pk=owner_id).first() if owner_id else None
    if not owner:
        raise WorkflowError('指定责任人不存在。', code='owner_not_found', status_code=404)
    if not (getattr(owner, 'is_teacher', False) or getattr(owner, 'is_admin', False) or owner.is_superuser):
        raise WorkflowError('责任人必须是教师或管理员。', code='invalid_owner')
    if ticket.status not in (
        constants.STATUS_PENDING_FACT_REVIEW,
        constants.STATUS_PENDING_EVIDENCE,
        constants.STATUS_REOPENED,
    ):
        raise WorkflowError('当前状态不能分配。', code='invalid_status')
    from_status = ticket.status
    to_status = constants.STATUS_PENDING_FACT_REVIEW if ticket.status == constants.STATUS_REOPENED else ticket.status
    ticket.owner = owner
    ticket.owner_role = payload.get('owner_role') or ticket.owner_role
    ticket.assigned_at = now()
    ticket.status = to_status
    ticket.version += 1
    ticket.save(update_fields=[
        'owner', 'owner_role', 'assigned_at', 'status', 'version', 'updated_at',
    ])
    action, link = record_action(
        ticket, action='assign', actor=actor,
        from_status=from_status, to_status=to_status,
        reason=payload.get('reason') or '管理员分配责任人。',
        metadata={'owner_id': owner.id, 'owner_role': ticket.owner_role},
        event_type=(
            constants.EVENT_FEEDBACK_STATUS_CHANGED
            if from_status != to_status else ''
        ),
    )
    return ticket, action, link


def _triage(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status == constants.STATUS_DUPLICATE:
        raise WorkflowError('重复记录不作为独立待办处理。', code='duplicate_record')
    impact = payload.get('impact_level') or ticket.impact_level
    novelty = payload.get('novelty') or ticket.novelty
    if impact not in dict(constants.IMPACT_CHOICES):
        raise WorkflowError('未知影响等级。', code='invalid_impact')
    if novelty not in dict(constants.NOVELTY_CHOICES):
        raise WorkflowError('未知新颖性。', code='invalid_novelty')
    conflict = payload.get('conflict_flag')
    if conflict is None:
        conflict = ticket.conflict_flag
    from_status = ticket.status
    ticket.impact_level = impact
    ticket.novelty = novelty
    ticket.conflict_flag = bool(conflict)
    ticket.version += 1
    ticket.save(update_fields=[
        'impact_level', 'novelty', 'conflict_flag', 'version', 'updated_at',
    ])
    action, link = record_action(
        ticket, action='triage', actor=actor,
        from_status=from_status, to_status=from_status,
        reason=payload.get('reason') or '教师登记冲突、影响和新颖性。',
        metadata={
            'impact_level': impact,
            'novelty': novelty,
            'conflict_flag': ticket.conflict_flag,
        },
    )
    return ticket, action, link


def _request_evidence(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status not in (
        constants.STATUS_PENDING_FACT_REVIEW,
        constants.STATUS_PENDING_EVIDENCE,
        constants.STATUS_REOPENED,
    ):
        raise WorkflowError('当前状态不能发起补证。', code='invalid_status')
    requested = payload.get('missing_slots') or list(ticket.missing_evidence or [])
    required = set(constants.required_slots(ticket.category, ticket.issue_type))
    invalid = [slot for slot in requested if slot not in required]
    if invalid:
        raise WorkflowError('补证槽不属于该类别必需证据。', code='invalid_evidence_slot', extra={'slots': invalid})
    if not requested:
        raise WorkflowError('没有需要补充的证据槽。', code='evidence_not_missing')
    reason = _require_reason(payload)
    due_at = _parse_dt(payload.get('due_at'))
    owner_id = payload.get('owner_id')
    if owner_id:
        owner = User.objects.filter(pk=owner_id).first()
        if not owner:
            raise WorkflowError('补证责任人不存在。', code='owner_not_found', status_code=404)
        ticket.owner = owner
        ticket.assigned_at = now()
    from_status = ticket.status
    ticket.status = constants.STATUS_PENDING_EVIDENCE
    ticket.due_at = due_at
    ticket.version += 1
    ticket.save(update_fields=[
        'status', 'due_at', 'owner', 'assigned_at', 'version', 'updated_at',
    ])
    action, link = record_action(
        ticket, action='request_evidence', actor=actor,
        from_status=from_status, to_status=constants.STATUS_PENDING_EVIDENCE,
        reason=reason,
        metadata={'missing_slots': requested, 'due_at': due_at.isoformat() if due_at else None},
        event_type=constants.EVENT_FEEDBACK_REVIEWED,
    )
    return ticket, action, link


def _confirm(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status not in (
        constants.STATUS_PENDING_FACT_REVIEW,
        constants.STATUS_PENDING_EVIDENCE,
        constants.STATUS_REOPENED,
    ):
        raise WorkflowError('只有“待事实复核”的工单可以确认。', code='invalid_status')
    _confirm_gates(ticket)
    destination = _validate_destination(
        payload.get('handling_destination') or ticket.handling_destination
        or constants.default_destination(ticket.category, ticket.issue_type)
    )
    _check_special_destination(ticket, destination)
    reason = _require_reason(payload)
    review = create_review(
        ticket, conclusion=constants.STATUS_CONFIRMED, reason=reason,
        evidence_refs=payload.get('evidence_refs') or [], reviewer=actor,
    )
    from_status = ticket.status
    ticket.status = constants.STATUS_CONFIRMED
    ticket.current_review = review
    ticket.reviewed_at = now()
    ticket.handling_destination = destination
    ticket.owner_role = payload.get('owner_role') or ticket.owner_role
    ticket.version += 1
    ticket.save(update_fields=[
        'status', 'current_review', 'reviewed_at', 'handling_destination',
        'owner_role', 'version', 'updated_at',
    ])
    action, link = record_action(
        ticket, action='confirm', actor=actor,
        from_status=from_status, to_status=constants.STATUS_CONFIRMED,
        reason=reason,
        metadata={
            'review_id': str(review.review_id),
            'handling_destination': destination,
            'candidate_eligible': ticket.candidate_eligible,
        },
        event_type=constants.EVENT_FEEDBACK_REVIEWED,
    )
    return ticket, action, link


def _reject(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status not in (
        constants.STATUS_PENDING_FACT_REVIEW,
        constants.STATUS_PENDING_EVIDENCE,
        constants.STATUS_REOPENED,
    ):
        raise WorkflowError('当前状态不能驳回。', code='invalid_status')
    reason = _require_reason(payload)
    review = create_review(
        ticket, conclusion=constants.STATUS_REJECTED, reason=reason,
        evidence_refs=payload.get('evidence_refs') or [], reviewer=actor,
    )
    from_status = ticket.status
    ticket.status = constants.STATUS_REJECTED
    ticket.current_review = review
    ticket.reviewed_at = now()
    ticket.version += 1
    ticket.save(update_fields=[
        'status', 'current_review', 'reviewed_at', 'version', 'updated_at',
    ])
    action, link = record_action(
        ticket, action='reject', actor=actor,
        from_status=from_status, to_status=constants.STATUS_REJECTED,
        reason=reason,
        metadata={'review_id': str(review.review_id)},
        event_type=constants.EVENT_FEEDBACK_REVIEWED,
    )
    return ticket, action, link


def _revise_review(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status not in (constants.STATUS_CONFIRMED, constants.STATUS_REJECTED):
        raise WorkflowError('只有已确认或已驳回的工单可以追加复核更正。', code='invalid_status')
    conclusion = payload.get('conclusion')
    if conclusion not in (constants.STATUS_CONFIRMED, constants.STATUS_REJECTED):
        raise WorkflowError('复核结论必须为 confirmed 或 rejected。', code='invalid_conclusion')
    reason = _require_reason(payload)
    if conclusion == constants.STATUS_CONFIRMED:
        _confirm_gates(ticket)
        destination = ticket.handling_destination
        _check_special_destination(ticket, destination)
    previous = ticket.current_review
    review = create_review(
        ticket, conclusion=conclusion, reason=reason,
        evidence_refs=payload.get('evidence_refs') or [], reviewer=actor,
    )
    from_status = ticket.status
    ticket.status = conclusion
    ticket.current_review = review
    ticket.reviewed_at = now()
    ticket.version += 1
    ticket.save(update_fields=[
        'status', 'current_review', 'reviewed_at', 'version', 'updated_at',
    ])
    action, link = record_action(
        ticket, action='revise_review', actor=actor,
        from_status=from_status, to_status=conclusion,
        reason=reason,
        metadata={
            'review_id': str(review.review_id),
            'previous_review_id': str(previous.review_id) if previous else '',
        },
        event_type=constants.EVENT_FEEDBACK_REVIEWED,
    )
    return ticket, action, link


def _start_handling(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status != constants.STATUS_CONFIRMED:
        raise WorkflowError('只有已确认的工单可以开始人工处理。', code='invalid_status')
    destination = _validate_destination(
        payload.get('handling_destination') or ticket.handling_destination
        or constants.default_destination(ticket.category, ticket.issue_type)
    )
    _check_special_destination(ticket, destination)
    handling_action = str(payload.get('handling_action') or '').strip()
    if not handling_action:
        raise WorkflowError('必须填写处理动作。', code='handling_action_required')
    referral = None
    if destination in constants.REFERRAL_DESTINATIONS:
        referral = _ensure_referral(
            ticket, destination=destination, actor=actor,
            note=payload.get('referral_note') or f'处理去向：{constants.DESTINATION_LABELS.get(destination, destination)}。',
        )
    from_status = ticket.status
    ticket.status = constants.STATUS_HANDLING
    ticket.handling_destination = destination
    ticket.handling_owner = actor
    ticket.handling_started_at = now()
    ticket.handling_action = handling_action
    ticket.handling_note = str(payload.get('handling_note') or '').strip()
    ticket.version += 1
    ticket.save(update_fields=[
        'status', 'handling_destination', 'handling_owner', 'handling_started_at',
        'handling_action', 'handling_note', 'version', 'updated_at',
    ])
    action, link = record_action(
        ticket, action='start_handling', actor=actor,
        from_status=from_status, to_status=constants.STATUS_HANDLING,
        reason=payload.get('reason') or '开始人工处理。',
        metadata={
            'handling_action': handling_action,
            'handling_destination': destination,
            'referral_id': str(referral.referral_id) if referral else '',
        },
        event_type=constants.EVENT_FEEDBACK_HANDLING_STARTED,
    )
    return ticket, action, link


def _refer(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status == constants.STATUS_DUPLICATE:
        raise WorkflowError('重复记录不单独转交。', code='duplicate_record')
    destination = payload.get('destination')
    if destination not in constants.REFERRAL_DESTINATIONS:
        raise WorkflowError('转交去向必须是模块六、模块一、课程材料或平台维护。', code='invalid_destination')
    note = _require_reason(payload)
    referral = FeedbackReferral.objects.create(
        ticket=ticket,
        destination=destination,
        note=note,
        external_ref=str(payload.get('external_ref') or '').strip(),
        status=constants.REFERRAL_PENDING,
        created_by=actor,
    )
    from_status = ticket.status
    ticket.version += 1
    ticket.save(update_fields=['version', 'updated_at'])
    action, link = record_action(
        ticket, action='refer', actor=actor,
        from_status=from_status, to_status=from_status,
        reason=note,
        metadata={
            'referral_id': str(referral.referral_id),
            'destination': destination,
            'external_ref': referral.external_ref,
        },
    )
    return ticket, action, link


def _ack_referral(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    referral_id = payload.get('referral_id')
    referral = ticket.referrals.filter(referral_id=referral_id).first()
    if not referral:
        raise WorkflowError('转交记录不存在。', code='referral_not_found', status_code=404)
    outcome = payload.get('referral_status') or constants.REFERRAL_ACKNOWLEDGED
    if outcome not in (constants.REFERRAL_ACKNOWLEDGED, constants.REFERRAL_DECLINED):
        raise WorkflowError('接收状态必须为 acknowledged 或 declined。', code='invalid_referral_status')
    note = str(payload.get('ack_note') or '').strip()
    if outcome == constants.REFERRAL_DECLINED and not note:
        raise WorkflowError('退回转交时必须说明原因。', code='ack_note_required')
    from_status = ticket.status
    referral.status = outcome
    referral.acknowledged_by = actor
    referral.acknowledged_at = now()
    referral.ack_note = note
    if payload.get('external_ref'):
        referral.external_ref = str(payload['external_ref']).strip()
    referral.save(update_fields=[
        'status', 'acknowledged_by', 'acknowledged_at', 'ack_note', 'external_ref',
    ])
    ticket.version += 1
    ticket.save(update_fields=['version', 'updated_at'])
    action, link = record_action(
        ticket, action='ack_referral', actor=actor,
        from_status=from_status, to_status=from_status,
        reason=note or '接收方确认转交。',
        metadata={
            'referral_id': str(referral.referral_id),
            'destination': referral.destination,
            'referral_status': referral.status,
            'external_ref': referral.external_ref,
        },
    )
    return ticket, action, link


def _handle(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status != constants.STATUS_HANDLING:
        raise WorkflowError('只有“人工处理中”的工单可以标记已处理。', code='invalid_status')
    pending = list(ticket.referrals.filter(status=constants.REFERRAL_PENDING))
    if pending:
        raise WorkflowError(
            '仍有转交尚未被接收方确认，不能标记已处理。',
            code='referral_pending',
            extra={'referral_ids': [str(item.referral_id) for item in pending]},
        )
    required_destination = _required_destination(ticket)
    if required_destination:
        acknowledged = ticket.referrals.filter(
            destination=required_destination,
            status=constants.REFERRAL_ACKNOWLEDGED,
        ).exists()
        if not acknowledged:
            raise WorkflowError(
                '该问题必须由对应负责人确认接收后才能标记已处理。',
                code='referral_required',
                extra={'required_destination': required_destination},
            )
    note = str(payload.get('handling_note') or '').strip()
    if not (note or ticket.handling_action or ticket.handling_note):
        raise WorkflowError('必须记录处理动作或处理说明。', code='handling_note_required')
    from_status = ticket.status
    ticket.status = constants.STATUS_HANDLED
    ticket.handled_at = now()
    ticket.handling_note = note or ticket.handling_note
    ticket.version += 1
    ticket.save(update_fields=[
        'status', 'handled_at', 'handling_note', 'version', 'updated_at',
    ])
    action, link = record_action(
        ticket, action='handle', actor=actor,
        from_status=from_status, to_status=constants.STATUS_HANDLED,
        reason=payload.get('reason') or note or '人工处理动作已完成。',
        metadata={
            'handling_action': ticket.handling_action,
            'handling_destination': ticket.handling_destination,
            'effect_status': ticket.effect_status,
            'note': '处理完成不等于教学效果已验证，也不等于新规则已生效。',
        },
        event_type=constants.EVENT_FEEDBACK_HANDLED,
    )
    return ticket, action, link


def _reopen(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status not in constants.REOPENABLE_STATUSES:
        raise WorkflowError('当前状态不能重开。', code='invalid_status')
    reason = _require_reason(payload)
    from_status = ticket.status
    ticket.status = constants.STATUS_REOPENED
    ticket.reopened_at = now()
    ticket.version += 1
    ticket.save(update_fields=['status', 'reopened_at', 'version', 'updated_at'])
    action, link = record_action(
        ticket, action='reopen', actor=actor,
        from_status=from_status, to_status=constants.STATUS_REOPENED,
        reason=reason,
        metadata={'original_review_preserved': True},
        event_type=constants.EVENT_FEEDBACK_REOPENED,
    )
    return ticket, action, link


def _note(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    note = _require_reason(payload, code='note_required')
    from_status = ticket.status
    ticket.version += 1
    ticket.save(update_fields=['version', 'updated_at'])
    action, link = record_action(
        ticket, action='note', actor=actor,
        from_status=from_status, to_status=from_status,
        reason=note,
        visibility=constants.VISIBILITY_STAFF,
    )
    return ticket, action, link


def _set_effect(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status not in constants.EFFECT_EDITABLE_STATUSES:
        raise WorkflowError('当前状态不能登记教学效果。', code='invalid_status')
    effect_status = payload.get('effect_status')
    if effect_status not in dict(constants.EFFECT_CHOICES):
        raise WorkflowError('未知教学效果状态。', code='invalid_effect_status')
    note = str(payload.get('effect_note') or '').strip()
    retest_fact_ref = str(payload.get('retest_fact_ref') or '').strip()
    retest_attempt_ref = str(payload.get('retest_attempt_ref') or '').strip()

    if effect_status == constants.EFFECT_VERIFIED:
        if not retest_fact_ref or not retest_attempt_ref:
            raise WorkflowError(
                '标记“已验证”必须引用真实复测事实和复测尝试。',
                code='retest_evidence_required',
            )
        fact = VerificationFact.objects.filter(
            fact_id=retest_fact_ref, student=ticket.student,
        ).first()
        if not fact:
            raise WorkflowError(
                '未找到该复测事实；不能凭空登记教学效果。',
                code='retest_fact_not_found',
                status_code=404,
            )
        if fact.outcome != 'passed':
            raise WorkflowError(
                '复测事实不是通过结论，不能标记“已验证”。',
                code='retest_not_passed',
                extra={'outcome': fact.outcome},
            )
        if fact.attempt_id and str(fact.attempt_id) != retest_attempt_ref:
            raise WorkflowError(
                '复测事实与复测尝试不一致。',
                code='retest_attempt_mismatch',
            )
        if ticket.attempt_id:
            if not fact.retest_of_attempt_id or str(fact.retest_of_attempt_id) != str(ticket.attempt.attempt_id):
                raise WorkflowError(
                    '该事实没有关联原尝试，不能作为本次反馈的复测证据。',
                    code='retest_link_missing',
                )
        if fact.independence != 'independent':
            note = (note + ' ' if note else '') + '复测为受助/未知独立性；只能证明完成，不能证明无提示保持。'
    elif effect_status == constants.EFFECT_INSUFFICIENT and not note:
        raise WorkflowError('标记证据不足时必须说明原因。', code='effect_note_required')

    from_status = ticket.status
    ticket.effect_status = effect_status
    ticket.effect_note = note
    ticket.retest_fact_ref = retest_fact_ref
    ticket.retest_attempt_ref = retest_attempt_ref
    ticket.effect_updated_at = now()
    ticket.version += 1
    ticket.save(update_fields=[
        'effect_status', 'effect_note', 'retest_fact_ref', 'retest_attempt_ref',
        'effect_updated_at', 'version', 'updated_at',
    ])
    action, link = record_action(
        ticket, action='set_effect', actor=actor,
        from_status=from_status, to_status=from_status,
        reason=payload.get('reason') or note or '登记教学效果状态。',
        metadata={
            'effect_status': effect_status,
            'retest_fact_ref': retest_fact_ref,
            'retest_attempt_ref': retest_attempt_ref,
            'ticket_status_unchanged': True,
        },
        event_type=constants.EVENT_FEEDBACK_EFFECT_UPDATED,
    )
    return ticket, action, link


def _confirm_duplicate(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status == constants.STATUS_DUPLICATE:
        raise WorkflowError('该工单已经是重复记录。', code='already_duplicate')
    main_id = payload.get('main_ticket_id')
    main = FeedbackTicket.objects.select_for_update().filter(feedback_id=main_id).first()
    if not main or main.pk == ticket.pk:
        raise WorkflowError('主记录不存在或与当前工单相同。', code='main_ticket_not_found', status_code=404)
    if main.duplicate_of_id:
        raise WorkflowError('主记录本身不能是重复记录。', code='main_ticket_is_duplicate')
    if main.student_id != ticket.student_id:
        raise WorkflowError('不同学生的反馈不能合并为重复记录。', code='student_mismatch')
    reason = _require_reason(payload)
    from_status = ticket.status
    ticket.duplicate_of = main
    ticket.status = constants.STATUS_DUPLICATE
    ticket.version += 1
    ticket.save(update_fields=['duplicate_of', 'status', 'version', 'updated_at'])
    FeedbackRelation.objects.get_or_create(
        from_ticket=main, to_ticket=ticket, relation_type='duplicate',
        defaults={'created_by': actor, 'note': reason},
    )
    action, link = record_action(
        ticket, action='confirm_duplicate', actor=actor,
        from_status=from_status, to_status=constants.STATUS_DUPLICATE,
        reason=reason,
        metadata={'duplicate_of': str(main.feedback_id)},
        event_type=constants.EVENT_FEEDBACK_DEDUPLICATED,
    )
    return ticket, action, link


def _split_duplicate(actor, ticket, payload):
    _require_teacher(actor)
    ticket = _locked(ticket)
    _check_version(ticket, payload)
    if ticket.status != constants.STATUS_DUPLICATE or not ticket.duplicate_of_id:
        raise WorkflowError('只有重复记录可以拆分。', code='not_duplicate')
    reason = _require_reason(payload)
    previous_main = ticket.duplicate_of
    from_status = ticket.status
    ticket.duplicate_of = None
    ticket.status = (
        constants.STATUS_PENDING_EVIDENCE
        if ticket.missing_evidence else constants.STATUS_PENDING_FACT_REVIEW
    )
    ticket.version += 1
    ticket.save(update_fields=['duplicate_of', 'status', 'version', 'updated_at'])
    FeedbackRelation.objects.get_or_create(
        from_ticket=previous_main, to_ticket=ticket, relation_type='split_from',
        defaults={'created_by': actor, 'note': reason},
    )
    action, link = record_action(
        ticket, action='split_duplicate', actor=actor,
        from_status=from_status, to_status=ticket.status,
        reason=reason,
        metadata={'previous_duplicate_of': str(previous_main.feedback_id)},
        event_type=constants.EVENT_FEEDBACK_DEDUPLICATED,
    )
    return ticket, action, link


HANDLERS = {
    'claim': _claim,
    'assign': _assign,
    'triage': _triage,
    'request_evidence': _request_evidence,
    'confirm': _confirm,
    'reject': _reject,
    'revise_review': _revise_review,
    'start_handling': _start_handling,
    'refer': _refer,
    'ack_referral': _ack_referral,
    'handle': _handle,
    'reopen': _reopen,
    'note': _note,
    'set_effect': _set_effect,
    'confirm_duplicate': _confirm_duplicate,
    'split_duplicate': _split_duplicate,
}


@transaction.atomic
def perform_action(actor, ticket, action, payload):
    handler = HANDLERS.get(action)
    if handler is None:
        raise WorkflowError('未知处理动作。', code='unknown_action', status_code=400)
    ticket, action_row, link = handler(actor, ticket, payload)
    sync = sync_links([link] if link else [])
    return ticket, action_row, sync
