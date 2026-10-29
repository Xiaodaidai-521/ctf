"""Teaching-configuration candidates (module 7, phase 3).

The state machine is real and enforced on the server.  Writes are gated by
settings so the first phase cannot publish a configuration by accident:

* ``FEEDBACK_PHASE3_ENABLED``        — create/edit/confirm/evaluate/approve
* ``FEEDBACK_PHASE3_RELEASE_ENABLED`` — activate / observe / roll back

Every transition re-checks the exact configuration digest and the module-8
report reference, so a stale approval can never be reused.
"""

import hashlib
import json

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .. import constants
from ..models import FeedbackCandidate, FeedbackCandidateEvent, FeedbackIssueGroup


class CandidateError(ValueError):
    def __init__(self, message, code='candidate_invalid'):
        super().__init__(message)
        self.code = code


def phase3_enabled():
    return bool(getattr(settings, 'FEEDBACK_PHASE3_ENABLED', False))


def release_enabled():
    return bool(getattr(settings, 'FEEDBACK_PHASE3_RELEASE_ENABLED', False))


def require_write():
    if not phase3_enabled():
        raise CandidateError(
            '第三阶段候选管理未启用；本轮只采集与处理反馈。',
            code=constants.PHASE3_WRITE_DISABLED,
        )


def require_release():
    if not release_enabled():
        raise CandidateError(
            '教学配置生效与回退未启用。',
            code=constants.PHASE3_RELEASE_DISABLED,
        )


def digest_of(payload):
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _transition(candidate, to_state, *, actor, action, note=''):
    allowed = constants.CANDIDATE_TRANSITIONS.get(candidate.state, set())
    if to_state not in allowed:
        raise CandidateError(
            f'不允许从 {candidate.state} 进入 {to_state}。'
        )
    previous = candidate.state
    candidate.state = to_state
    candidate.save(update_fields=['state', 'updated_at'])
    FeedbackCandidateEvent.objects.create(
        candidate=candidate,
        action=action,
        from_state=previous,
        to_state=to_state,
        note=note,
        actor=actor,
    )
    return candidate


@transaction.atomic
def create_candidate(*, actor, title, issue_group_ids, baseline_config_version,
                     candidate_config_version, single_changed_factor,
                     target_task_versions, baseline_config, candidate_config,
                     rollback_version, expected_risk='', excluded_scope=None):
    require_write()
    if not title.strip():
        raise CandidateError('候选名称不能为空。')
    if not single_changed_factor.strip():
        raise CandidateError('必须写明唯一改动因素。')
    if baseline_config_version == candidate_config_version:
        raise CandidateError('候选配置版本必须与基准不同。')

    groups = list(FeedbackIssueGroup.objects.filter(group_id__in=issue_group_ids))
    if len(groups) != len(set(issue_group_ids)):
        raise CandidateError('存在找不到的问题组。')
    if not groups:
        raise CandidateError('候选必须引用至少一个已确认问题组。')
    unconfirmed = [group.title for group in groups if not group.is_confirmed]
    if unconfirmed:
        raise CandidateError(f'问题组尚未确认：{"、".join(unconfirmed[:3])}')
    with_missing_evidence = [
        group.title for group in groups
        if (group.counts or {}).get('missing_evidence')
    ]
    if with_missing_evidence:
        raise CandidateError(
            f'问题组仍含缺证反馈，不能作为候选依据：{"、".join(with_missing_evidence[:3])}'
        )

    candidate = FeedbackCandidate.objects.create(
        title=title.strip(),
        baseline_config_version=baseline_config_version,
        candidate_config_version=candidate_config_version,
        single_changed_factor=single_changed_factor.strip(),
        target_task_versions=list(target_task_versions or []),
        excluded_scope=list(excluded_scope or []),
        expected_risk=expected_risk,
        rollback_version=rollback_version,
        baseline_config=baseline_config or {},
        candidate_config=candidate_config or {},
        baseline_config_digest=digest_of(baseline_config or {}),
        config_digest=digest_of(candidate_config or {}),
        owner=actor,
    )
    candidate.issue_groups.set(groups)
    FeedbackCandidateEvent.objects.create(
        candidate=candidate,
        action='created',
        to_state=constants.CANDIDATE_DRAFT,
        actor=actor,
    )
    return candidate


@transaction.atomic
def submit_for_evaluation(candidate, *, actor, note=''):
    require_write()
    if not candidate.issue_groups.exists():
        raise CandidateError('候选没有引用问题组。')
    candidate.config_digest = digest_of(candidate.candidate_config or {})
    candidate.baseline_config_digest = digest_of(candidate.baseline_config or {})
    candidate.save(update_fields=['config_digest', 'baseline_config_digest', 'updated_at'])
    return _transition(
        candidate, constants.CANDIDATE_PENDING_EVAL,
        actor=actor, action='submitted_for_evaluation', note=note,
    )


def _trusted_report(candidate, report):
    from django.apps import apps

    if not apps.is_installed('evaluation_center'):
        raise CandidateError('模块八评测记录未接通，不能登记或放行报告。')
    from evaluation_center.evaluations import EvaluationError, resolve_report

    current = FeedbackCandidate.objects.get(pk=candidate.pk)
    try:
        return resolve_report(current, report)
    except EvaluationError as exc:
        raise CandidateError(str(exc)) from exc


@transaction.atomic
def attach_report(candidate, *, actor, report):
    """Attach a module-8 report reference.  The report itself stays in module 8."""

    require_write()
    required = ('run_id', 'report_id', 'report_version', 'report_digest', 'recommendation')
    missing = [key for key in required if not report.get(key)]
    if missing:
        raise CandidateError(f'报告引用缺少字段：{", ".join(missing)}')
    if report['recommendation'] not in dict(constants.REPORT_RECOMMENDATION_CHOICES):
        raise CandidateError('报告建议取值不合法。')
    if not report.get('completed'):
        raise CandidateError('评测未完成，不能作为审批依据。')
    if report.get('missing_cases'):
        raise CandidateError('评测存在缺失案例，不能作为审批依据。')
    if report.get('candidate_config_digest') and report['candidate_config_digest'] != candidate.config_digest:
        raise CandidateError('报告针对的候选配置摘要与当前配置不一致。')

    report = _trusted_report(candidate, report)
    candidate.evaluation_report_ref = {
        **report,
        'attached_at': timezone.now().isoformat(),
        'attached_by': actor.id,
    }
    candidate.save(update_fields=['evaluation_report_ref', 'updated_at'])
    FeedbackCandidateEvent.objects.create(
        candidate=candidate,
        action='report_attached',
        from_state=candidate.state,
        to_state=candidate.state,
        note=f"module8 report {report['report_id']} v{report['report_version']}",
        actor=actor,
    )
    if candidate.state == constants.CANDIDATE_PENDING_EVAL:
        return _transition(
            candidate, constants.CANDIDATE_EVALUATING,
            actor=actor, action='evaluation_started',
        )
    return candidate


@transaction.atomic
def complete_evaluation(candidate, *, actor, note=''):
    require_write()
    report = candidate.evaluation_report_ref or {}
    if not report.get('report_id'):
        raise CandidateError('缺少模块八评测报告，不能进入审批。')
    report = _trusted_report(candidate, report)
    if report.get('recommendation') == constants.REPORT_RECOMMENDATION_PASS:
        return _transition(
            candidate, constants.CANDIDATE_PENDING_APPROVAL,
            actor=actor, action='evaluation_passed', note=note,
        )
    return _transition(
        candidate, constants.CANDIDATE_NEEDS_REVISION,
        actor=actor, action='evaluation_not_passed', note=note or report.get('recommendation', ''),
    )


@transaction.atomic
def approve(candidate, *, approver, scope, observation_window, rollback_condition,
            approver_may_release=False):
    require_write()
    if candidate.state != constants.CANDIDATE_PENDING_APPROVAL:
        raise CandidateError('只有待审批的候选可以审批。')
    report = _trusted_report(candidate, candidate.evaluation_report_ref or {})
    if report.get('recommendation') != constants.REPORT_RECOMMENDATION_PASS:
        raise CandidateError('评测报告未给出通过建议。')
    if not report.get('report_digest'):
        raise CandidateError('评测报告缺少摘要，无法绑定审批。')
    if candidate.owner_id == approver.id and not approver_may_release:
        raise CandidateError('候选作者不能独自完成审批；需另一名授权审批人。')
    for field, value in (
        ('scope', scope), ('observation_window', observation_window),
        ('rollback_condition', rollback_condition),
    ):
        if not str(value or '').strip():
            raise CandidateError(f'审批必须填写 {field}。')

    candidate.approval = {
        'approver_id': approver.id,
        'approved_at': timezone.now().isoformat(),
        'approved_config_digest': candidate.config_digest,
        'approved_report_id': report.get('report_id'),
        'approved_report_digest': report.get('report_digest'),
        'approved_baseline_config_digest': candidate.baseline_config_digest,
        'scope': scope,
        'observation_window': observation_window,
        'rollback_condition': rollback_condition,
    }
    candidate.save(update_fields=['approval', 'updated_at'])
    return _transition(
        candidate, constants.CANDIDATE_APPROVED_PENDING_RELEASE,
        actor=approver, action='approved',
    )


def _approval_is_current(candidate):
    approval = candidate.approval or {}
    if not approval:
        return False, '没有审批记录。'
    if approval.get('approved_config_digest') != candidate.config_digest:
        return False, '候选配置在审批后已变化，旧审批失效。'
    if approval.get('approved_baseline_config_digest') != candidate.baseline_config_digest:
        return False, '基准配置在审批后已变化，旧审批失效。'
    report = candidate.evaluation_report_ref or {}
    if approval.get('approved_report_id') != report.get('report_id'):
        return False, '评测报告已变化，旧审批失效。'
    if approval.get('approved_report_digest') != report.get('report_digest'):
        return False, '评测报告内容已变化，旧审批失效。'
    try:
        _trusted_report(candidate, report)
    except CandidateError as exc:
        return False, str(exc)
    return True, ''


@transaction.atomic
def activate(candidate, *, operator, applicable_future_tasks, approver_may_release=False):
    require_release()
    if candidate.state != constants.CANDIDATE_APPROVED_PENDING_RELEASE:
        raise CandidateError('只有已批准待发布的候选可以生效。')
    ok, reason = _approval_is_current(candidate)
    if not ok:
        raise CandidateError(reason)
    if not set(applicable_future_tasks or []).issubset(set(candidate.target_task_versions or [])):
        raise CandidateError('发布任务范围不能超出已评测范围。')
    approval = candidate.approval or {}
    if approval.get('approver_id') == operator.id and not approver_may_release:
        raise CandidateError('审批人与发布人不能是同一人。')

    candidate.activation = {
        'activated_by': operator.id,
        'activated_at': timezone.now().isoformat(),
        'applicable_future_tasks': list(applicable_future_tasks or []),
        'effective_config_digest': candidate.config_digest,
        'affects_future_tasks_only': True,
    }
    candidate.observation = {
        'status': constants.OBSERVATION_OBSERVING,
        'started_at': timezone.now().isoformat(),
    }
    candidate.save(update_fields=['activation', 'observation', 'updated_at'])
    return _transition(
        candidate, constants.CANDIDATE_OBSERVING,
        actor=operator, action='activated',
    )


@transaction.atomic
def record_observation(candidate, *, actor, report_id='', status=None,
                       new_failures=None, normal_block_rate=None,
                       unauthorized_allow_rate=None, note=''):
    if candidate.state != constants.CANDIDATE_OBSERVING:
        raise CandidateError('只有观察中的候选可以记录观察。')
    if status and status not in dict(constants.OBSERVATION_STATUS_CHOICES):
        raise CandidateError('观察状态取值不合法。')
    observation = {
        **(candidate.observation or {}),
        'status': status or constants.OBSERVATION_OBSERVING,
        'report_id': report_id,
        'new_failures': new_failures,
        'normal_block_rate': normal_block_rate,
        'unauthorized_allow_rate': unauthorized_allow_rate,
        'updated_at': timezone.now().isoformat(),
        'note': note,
    }
    candidate.observation = observation
    candidate.save(update_fields=['observation', 'updated_at'])
    FeedbackCandidateEvent.objects.create(
        candidate=candidate,
        action='observation_recorded',
        from_state=candidate.state,
        to_state=candidate.state,
        note=note,
        actor=actor,
    )
    return candidate


@transaction.atomic
def mark_stable(candidate, *, actor, note=''):
    require_release()
    observation = candidate.observation or {}
    if observation.get('status') == constants.OBSERVATION_INSUFFICIENT:
        raise CandidateError('样本不足，不能标记为已稳定。')
    if observation.get('new_failures'):
        raise CandidateError('存在未解释的新失败，不能标记为已稳定。')
    return _transition(
        candidate, constants.CANDIDATE_STABLE,
        actor=actor, action='marked_stable', note=note,
    )


@transaction.atomic
def rollback(candidate, *, operator, reason, result):
    require_release()
    if candidate.state not in (constants.CANDIDATE_OBSERVING, constants.CANDIDATE_STABLE):
        raise CandidateError('只有观察中或已稳定的候选可以回退。')
    if result not in dict(constants.ROLLBACK_RESULT_CHOICES):
        raise CandidateError('回退结果取值不合法。')
    if not reason.strip():
        raise CandidateError('回退必须写明原因。')

    candidate.rollback = {
        'rolled_back_by': operator.id,
        'rolled_back_at': timezone.now().isoformat(),
        'from_version': candidate.candidate_config_version,
        'to_version': candidate.rollback_version,
        'reason': reason.strip(),
        'result': result,
    }
    candidate.save(update_fields=['rollback', 'updated_at'])
    if result == constants.ROLLBACK_UNKNOWN:
        FeedbackCandidateEvent.objects.create(
            candidate=candidate,
            action='rollback_unknown',
            from_state=candidate.state,
            to_state=candidate.state,
            note='回退结果未知，待对账；不得显示为成功。',
            actor=operator,
        )
        return candidate
    if result == constants.ROLLBACK_FAILED:
        FeedbackCandidateEvent.objects.create(
            candidate=candidate,
            action='rollback_failed',
            from_state=candidate.state,
            to_state=candidate.state,
            note=reason.strip(),
            actor=operator,
        )
        return candidate
    return _transition(
        candidate, constants.CANDIDATE_ROLLED_BACK,
        actor=operator, action='rolled_back', note=reason.strip(),
    )


def candidate_payload(candidate):
    ok, reason = _approval_is_current(candidate)
    return {
        'candidate_id': str(candidate.candidate_id),
        'title': candidate.title,
        'issue_group_ids': [
            str(group.group_id) for group in candidate.issue_groups.all()
        ],
        'baseline_config_version': candidate.baseline_config_version,
        'candidate_config_version': candidate.candidate_config_version,
        'single_changed_factor': candidate.single_changed_factor,
        'target_task_versions': candidate.target_task_versions,
        'excluded_scope': candidate.excluded_scope,
        'expected_risk': candidate.expected_risk,
        'rollback_version': candidate.rollback_version,
        'baseline_config_digest': candidate.baseline_config_digest,
        'config_digest': candidate.config_digest,
        'state': candidate.state,
        'state_label': constants.CANDIDATE_STATE_LABELS.get(candidate.state, candidate.state),
        'owner': candidate.owner_id,
        'evaluation_report_ref': candidate.evaluation_report_ref,
        'approval': candidate.approval,
        'approval_valid': ok,
        'approval_invalid_reason': reason,
        'activation': candidate.activation,
        'observation': candidate.observation,
        'rollback': candidate.rollback,
        'version': candidate.version,
        'phase3_write_enabled': phase3_enabled(),
        'release_enabled': release_enabled(),
        'events': [
            {
                'action': event.action,
                'from_state': event.from_state,
                'to_state': event.to_state,
                'note': event.note,
                'actor': event.actor_id,
                'created_at': event.created_at.isoformat(),
            }
            for event in candidate.events.order_by('-created_at')[:50]
        ],
        'created_at': candidate.created_at.isoformat(),
    }
