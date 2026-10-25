"""Deterministic program verification and result composition.

Program checks are configured on the task package (``validator.checks``).
There is no model call.  If a task only has a teacher rubric, the program result
is ``not_run`` and the result stays pending until a teacher reviews it.  If a
network task expects a service-side verifier that is not connected, the program
status is ``error`` — never a fabricated pass.
"""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import events, handoff, retest
from .. import constants
from ..models import (
    ManualReviewTask,
    SubmissionErrorCause,
    VerificationResult,
)


def _get_path(payload, path):
    value = payload
    for part in str(path).split('.'):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def verify_program(task, payload):
    spec = task.validator or {}
    verifier_type = spec.get('type') or ''
    version = spec.get('version') or constants.RULE_VERSION
    manual_required = bool(
        spec.get('manual_required', verifier_type in (
            'teacher_rubric', 'manual_only', 'rules+teacher_rubric',
        ))
    )

    if verifier_type in ('teacher_rubric', 'manual_only'):
        return {
            'status': constants.PROGRAM_NOT_RUN,
            'error': '',
            'version': version,
            'manual_required': True,
            'public_items': [],
            'internal': {'type': verifier_type, 'checks': []},
            'suggested_causes': [],
        }

    if verifier_type in ('server_verifier', 'external', 'isolated_challenge'):
        return {
            'status': constants.PROGRAM_ERROR,
            'error': 'server_evidence_not_connected',
            'version': version,
            'manual_required': manual_required,
            'public_items': [],
            'internal': {'type': verifier_type, 'error': 'server_evidence_not_connected'},
            'suggested_causes': [],
        }

    if verifier_type not in ('structured_rules', 'rules+teacher_rubric'):
        return {
            'status': constants.PROGRAM_ERROR,
            'error': 'unknown_verifier',
            'version': version,
            'manual_required': manual_required,
            'public_items': [],
            'internal': {'type': verifier_type, 'error': 'unknown_verifier'},
            'suggested_causes': [],
        }

    checks = spec.get('checks') or []
    if not checks:
        return {
            'status': constants.PROGRAM_ERROR,
            'error': 'verifier_not_configured',
            'version': version,
            'manual_required': manual_required,
            'public_items': [],
            'internal': {'type': verifier_type, 'checks': []},
            'suggested_causes': [],
        }

    public_items = []
    internal_checks = []
    suggested_causes = []
    all_passed = True
    for index, check in enumerate(checks, start=1):
        field = check.get('field')
        actual = _get_path(payload, field) if field else None
        if 'equals' in check:
            passed = actual == check.get('equals')
        elif 'in' in check:
            passed = actual in (check.get('in') or [])
        elif 'contains_all' in check:
            expected = set(check.get('contains_all') or [])
            passed = isinstance(actual, list) and expected.issubset(set(actual))
        elif 'contains_any' in check:
            expected = set(check.get('contains_any') or [])
            passed = isinstance(actual, list) and bool(expected & set(actual))
        elif 'required' in check:
            passed = actual not in (None, '', [], {})
        else:
            passed = False
        if not passed:
            all_passed = False
            cause = check.get('cause')
            if cause in dict(constants.ERROR_CAUSE_CHOICES) and cause not in suggested_causes:
                suggested_causes.append(cause)
        item_id = check.get('id') or f'check-{index}'
        public_items.append({
            'item_id': item_id,
            'kind': 'program',
            'label': check.get('label') or f'核验项 {index}',
            'status': 'passed' if passed else 'failed',
            'evidence_ref': check.get('evidence_ref', ''),
            'points': 1 if passed else 0,
            'max_points': 1,
            'score': 1 if passed else 0,
        })
        internal_checks.append({
            'item_id': item_id,
            'field': field,
            'expected': check.get('equals', check.get('in', check.get('contains_all', check.get('contains_any', check.get('required'))))),
            'actual': actual,
            'passed': passed,
        })

    return {
        'status': constants.PROGRAM_PASSED if all_passed else constants.PROGRAM_FAILED,
        'error': '',
        'version': version,
        'manual_required': manual_required,
        'public_items': public_items,
        'internal': {'type': verifier_type, 'checks': internal_checks},
        'suggested_causes': suggested_causes,
    }


def compute_overall(*, program_status, manual_status, manual_required, manual_decision=None, verification_error=''):
    if verification_error or program_status == constants.PROGRAM_ERROR:
        return constants.OVERALL_VERIFICATION_FAILED
    if program_status == constants.PROGRAM_FAILED:
        return constants.OVERALL_FAILED
    if program_status == constants.PROGRAM_PASSED:
        if manual_required and manual_status not in (constants.MANUAL_REVIEWED, constants.MANUAL_CORRECTED):
            return constants.OVERALL_PENDING_MANUAL
        if manual_required and manual_decision == 'fail':
            return constants.OVERALL_FAILED
        return constants.OVERALL_PASSED
    if program_status == constants.PROGRAM_NOT_RUN:
        if manual_required:
            if manual_status in (constants.MANUAL_REVIEWED, constants.MANUAL_CORRECTED):
                return constants.OVERALL_PASSED if manual_decision == 'pass' else constants.OVERALL_FAILED
            return constants.OVERALL_PENDING_MANUAL
        return constants.OVERALL_UNKNOWN
    return constants.OVERALL_PENDING


def rubric_snapshot():
    return [
        {'item_id': key, 'label': label, 'max_score': constants.RUBRIC_MAX_SCORE}
        for key, label in constants.RUBRIC_ITEMS
    ]


def _manual_items(scores=None):
    scores = scores or {}
    return [
        {
            'item_id': f'manual:{key}',
            'kind': 'manual',
            'label': label,
            'status': 'scored' if key in scores else 'pending',
            'score': scores.get(key, {}).get('score'),
            'max_points': constants.RUBRIC_MAX_SCORE,
            'evidence_ref': scores.get(key, {}).get('evidence', ''),
            'reason': scores.get(key, {}).get('reason', ''),
        }
        for key, label in constants.RUBRIC_ITEMS
    ]


def _record_suggested_causes(submission, causes):
    for cause in causes or []:
        SubmissionErrorCause.objects.update_or_create(
            submission=submission,
            cause=cause,
            defaults={
                'status': constants.CAUSE_SUGGESTED,
                'source': constants.CAUSE_SOURCE_SYSTEM,
                'note': '规则核验未通过项自动建议；需教师或学生确认。',
            },
        )


@transaction.atomic
def create_result_for_submission(submission, now=None):
    now = now or timezone.now()
    program = verify_program(submission.task, submission.payload)
    manual_required = program['manual_required']
    manual_status = constants.MANUAL_PENDING if manual_required else constants.MANUAL_NOT_APPLICABLE
    overall = compute_overall(
        program_status=program['status'],
        manual_status=manual_status,
        manual_required=manual_required,
        verification_error=program['error'],
    )
    item_results = list(program['public_items'])
    if manual_required:
        item_results.extend(_manual_items())

    result = VerificationResult.objects.create(
        submission=submission,
        attempt=submission.attempt,
        student=submission.student,
        task=submission.task,
        catalog=submission.catalog,
        version=1,
        revision=1,
        is_current=True,
        program_status=program['status'],
        manual_status=manual_status,
        overall_status=overall,
        independence=submission.independence,
        assistance_snapshot=submission.assistance_snapshot,
        item_results=item_results,
        program_result=program['internal'],
        verifier_version=program['version'],
        rubric_version=settings.MODULE6_RUBRIC_VERSION,
        verification_error=program['error'],
    )
    if manual_required:
        ManualReviewTask.objects.create(
            result=result,
            submission=submission,
            attempt=submission.attempt,
            student=submission.student,
            task=submission.task,
            catalog=submission.catalog,
            rubric=rubric_snapshot(),
            rubric_version=settings.MODULE6_RUBRIC_VERSION,
        )
    _record_suggested_causes(submission, program['suggested_causes'])

    events.emit_event(
        user=submission.student,
        event_type='verification_result',
        event_id=f'm6-result-{result.result_id}-r{result.revision}',
        catalog=submission.catalog,
        task=submission.task,
        attempt_id=submission.attempt.attempt_id,
        submission_id=submission.submission_id,
        result_id=result.result_id,
        capability_ids=[
            capability.stable_id for capability in submission.task.capabilities.all()
        ],
        evidence_ref=f'm6:{result.result_id}',
        verifier_version=result.verifier_version,
        extra={
            'program_status': result.program_status,
            'manual_status': result.manual_status,
            'overall_status': result.overall_status,
            'independence': result.independence,
            'save_status': 'saved',
        },
    )
    if overall in (
        constants.OVERALL_PASSED,
        constants.OVERALL_FAILED,
        constants.OVERALL_VERIFICATION_FAILED,
        constants.OVERALL_ENVIRONMENT_AFFECTED,
        constants.OVERALL_UNKNOWN,
    ):
        submission.attempt.status = 'verified'
        submission.attempt.save(update_fields=['status'])

    handoff.dispatch_result(result)
    retest.apply_result_to_assignment(result)
    return result


@transaction.atomic
def review_manual_task(task, *, reviewer, scores, decision, remarks, causes=None, admin_override=False):
    if task.status not in (constants.MANUAL_TASK_PENDING, constants.MANUAL_TASK_CLAIMED):
        raise ValueError('人工待办当前不可评阅。')
    if task.claimed_by_id and task.claimed_by_id != reviewer.id and not admin_override:
        raise PermissionError('该待办已被其他教师认领。')
    if decision not in ('pass', 'fail'):
        raise ValueError('评阅结论必须为 pass 或 fail。')

    normalized = {}
    for key, _label in constants.RUBRIC_ITEMS:
        item = scores.get(key) or {}
        score = item.get('score')
        if not isinstance(score, int) or score < 0 or score > constants.RUBRIC_MAX_SCORE:
            raise ValueError(f'量表项 {key} 的得分必须是 0—{constants.RUBRIC_MAX_SCORE}。')
        if score > 0 and not (item.get('evidence') and item.get('reason')):
            raise ValueError(f'量表项 {key} 得分大于 0 时必须记录证据定位和理由。')
        normalized[key] = {
            'score': score,
            'evidence': str(item.get('evidence') or ''),
            'reason': str(item.get('reason') or ''),
        }
    if not remarks.strip():
        raise ValueError('评阅说明不能为空。')

    result = task.result
    if result.manual_status == constants.MANUAL_CORRECTED:
        raise ValueError('该结果已进入更正版本，请在新版本上处理。')

    total = sum(item['score'] for item in normalized.values())
    task.status = constants.MANUAL_TASK_REVIEWED
    task.claimed_by = task.claimed_by or reviewer
    task.reviewed_by = reviewer
    task.reviewed_at = timezone.now()
    task.scores = normalized
    task.total_score = total
    task.decision = decision
    task.remarks = remarks
    task.save()

    result.manual_status = constants.MANUAL_REVIEWED
    result.manual_result = {
        'reviewer': reviewer.id,
        'reviewed_at': task.reviewed_at.isoformat(),
        'scores': normalized,
        'total_score': total,
        'decision': decision,
        'remarks': remarks,
        'rubric_version': task.rubric_version,
    }
    result.revision += 1
    result.overall_status = compute_overall(
        program_status=result.program_status,
        manual_status=result.manual_status,
        manual_required=True,
        manual_decision=decision,
        verification_error=result.verification_error,
    )
    program_items = [item for item in result.item_results if item.get('kind') == 'program']
    result.item_results = program_items + _manual_items(normalized)
    result.save()

    if causes:
        for cause in causes:
            if cause not in dict(constants.ERROR_CAUSE_CHOICES):
                raise ValueError(f'未知错因：{cause}')
            SubmissionErrorCause.objects.update_or_create(
                submission=task.submission,
                cause=cause,
                defaults={
                    'status': constants.CAUSE_CONFIRMED,
                    'source': constants.CAUSE_SOURCE_TEACHER,
                    'note': remarks,
                    'confirmed_by': reviewer,
                },
            )

    events.emit_event(
        user=task.student,
        event_type='teacher_help',
        event_id=f'm6-manual-{task.review_id}-r{result.revision}',
        catalog=task.catalog,
        task=task.task,
        attempt_id=task.attempt.attempt_id,
        submission_id=task.submission.submission_id,
        result_id=result.result_id,
        capability_ids=[
            capability.stable_id for capability in task.task.capabilities.all()
        ],
        evidence_ref=f'm6:{result.result_id}',
        verifier_version=result.verifier_version,
        extra={
            'manual_status': result.manual_status,
            'overall_status': result.overall_status,
            'rubric_version': task.rubric_version,
            'decision': decision,
        },
    )
    handoff.dispatch_result(result)
    retest.apply_result_to_assignment(result)
    return task
