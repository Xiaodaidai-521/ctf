"""Rule-based new-scenario retest assignment.

Selection never calls a model.  It excludes the original task, tasks already
attempted, tasks whose analysis the student has seen, unavailable environments
and milestone-only tasks.  If no candidate remains, the assignment is stored as
``pending_item`` for the course owner, not silently skipped.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import events
from .. import constants
from ..models import AssistanceRecord, RetestAssignment, SubmissionSnapshot


def _candidate_tasks(*, original_task, student, catalog):
    from learning_map.models import TaskPackage

    original_key = original_task.task_key
    attempted = set(
        SubmissionSnapshot.objects.filter(student=student, catalog=catalog)
        .values_list('task__task_key', flat=True)
    )
    exposed = set(
        AssistanceRecord.objects.filter(
            student=student,
            task__catalog=catalog,
            kind=constants.ASSISTANCE_KIND_ANALYSIS_VIEW,
        ).values_list('task__task_key', flat=True)
    )
    excluded_keys = {original_key, *attempted, *exposed}
    allowed_keys = set(original_task.retest_task_keys or [])

    queryset = TaskPackage.objects.filter(
        catalog=catalog,
        status='frozen',
    ).prefetch_related('capabilities').distinct()
    if allowed_keys:
        queryset = queryset.filter(task_key__in=allowed_keys)
    else:
        capability_ids = list(original_task.capabilities.values_list('id', flat=True))
        queryset = queryset.filter(capabilities__id__in=capability_ids)

    candidates = []
    capability_ids = set(original_task.capabilities.values_list('id', flat=True))
    for task in queryset.order_by('course_order', 'task_key', 'version'):
        if task.task_key in excluded_keys:
            continue
        if task.requires_milestone_i or not task.environment_available or task.materials_withdrawn:
            continue
        if not set(task.capabilities.values_list('id', flat=True)) & capability_ids:
            continue
        candidates.append(task)

    return candidates, {
        'original_task_key': original_key,
        'excluded_task_keys': sorted(excluded_keys),
        'allowed_pool_keys': sorted(allowed_keys),
        'candidate_task_keys': [task.task_key for task in candidates],
    }


def _select(candidates, student, submission):
    if not candidates:
        return None, 'no_candidate'
    index = (int(student.id) + int(submission.sequence)) % len(candidates)
    return candidates[index], 'deterministic_rotation'


def _retest_days():
    return int(getattr(settings, 'MODULE6_RETEST_INTERVAL_DAYS', 3))


def _grace_days():
    return int(getattr(settings, 'MODULE6_RETEST_GRACE_DAYS', 7))


@transaction.atomic
def schedule_retest(submission, *, now=None, due_days=None, actor=None):
    existing = RetestAssignment.objects.filter(original_submission=submission).first()
    if existing:
        return existing, False

    now = now or timezone.now()
    original_task = submission.task
    candidates, pool = _candidate_tasks(
        original_task=original_task,
        student=submission.student,
        catalog=submission.catalog,
    )
    selected, reason = _select(candidates, submission.student, submission)
    due_at = now + timedelta(days=due_days if due_days is not None else _retest_days())
    capability = original_task.capabilities.order_by('course_order', 'stable_id').first()
    assignment = RetestAssignment.objects.create(
        student=submission.student,
        catalog=submission.catalog,
        capability=capability,
        capability_ids=sorted(
            original_task.capabilities.values_list('stable_id', flat=True)
        ),
        original_attempt=submission.attempt,
        original_submission=submission,
        pool_snapshot=pool,
        selected_task=selected,
        selection_reason=reason,
        rule_version=constants.RULE_VERSION,
        status=constants.RETEST_SCHEDULED if selected else constants.RETEST_PENDING_ITEM,
        scheduled_at=now,
        due_at=due_at,
        grace_until=due_at + timedelta(days=_grace_days()),
    )
    events.emit_event(
        user=submission.student,
        event_type='retest_assign',
        event_id=f'm6-retest-assign-{assignment.assignment_id}',
        catalog=submission.catalog,
        task=selected or original_task,
        attempt_id=submission.attempt.attempt_id,
        submission_id=submission.submission_id,
        capability_ids=assignment.capability_ids,
        extra={
            'assignment_id': str(assignment.assignment_id),
            'status': assignment.status,
            'selected_task_key': selected.task_key if selected else '',
            'rule_version': constants.RULE_VERSION,
            'candidate_count': len(candidates),
        },
    )
    return assignment, True


def apply_result_to_assignment(result):
    assignment = RetestAssignment.objects.filter(started_attempt=result.attempt).first()
    if not assignment:
        return None
    if assignment.completed_submission_id and assignment.completed_submission_id != result.submission_id:
        return assignment

    assignment.completed_submission = result.submission
    assignment.completed_at = timezone.now()
    assignment.status = constants.RETEST_COMPLETED
    if result.overall_status == constants.OVERALL_PASSED:
        assignment.outcome = (
            constants.RETEST_OUTCOME_ASSISTED
            if result.independence == constants.INDEPENDENCE_ASSISTED
            else constants.RETEST_OUTCOME_PASSED
        )
    elif result.overall_status == constants.OVERALL_FAILED:
        assignment.outcome = constants.RETEST_OUTCOME_FAILED
    elif result.overall_status == constants.OVERALL_PENDING_MANUAL:
        assignment.outcome = constants.RETEST_OUTCOME_PENDING_MANUAL
    elif result.overall_status == constants.OVERALL_VERIFICATION_FAILED:
        assignment.outcome = constants.RETEST_OUTCOME_VERIFICATION_FAILED
    elif result.overall_status == constants.OVERALL_ENVIRONMENT_AFFECTED:
        assignment.outcome = constants.RETEST_OUTCOME_ENVIRONMENT
    else:
        assignment.outcome = constants.RETEST_OUTCOME_UNKNOWN
    assignment.save()
    events.emit_event(
        user=result.student,
        event_type='retest_assign',
        event_id=f'm6-retest-result-{assignment.assignment_id}-{result.result_id}-r{result.revision}',
        catalog=result.catalog,
        task=assignment.selected_task or result.task,
        attempt_id=result.attempt.attempt_id,
        submission_id=result.submission.submission_id,
        result_id=result.result_id,
        capability_ids=assignment.capability_ids,
        extra={
            'assignment_id': str(assignment.assignment_id),
            'status': assignment.status,
            'outcome': assignment.outcome,
            'original_attempt_id': str(assignment.original_attempt.attempt_id),
        },
    )
    return assignment


def process_due_retests(now=None, student=None):
    """Move scheduled → due, due → missed.  Never records a knowledge error."""

    now = now or timezone.now()
    queryset = RetestAssignment.objects.all()
    if student is not None:
        queryset = queryset.filter(student=student)
    due_count = 0
    missed_count = 0
    for assignment in queryset.filter(status=constants.RETEST_SCHEDULED, due_at__lte=now):
        assignment.status = constants.RETEST_DUE
        assignment.save(update_fields=['status', 'updated_at'])
        events.emit_event(
            user=assignment.student,
            event_type='retest_assign',
            event_id=f'm6-retest-due-{assignment.assignment_id}',
            catalog=assignment.catalog,
            task=assignment.selected_task,
            attempt_id=assignment.original_attempt.attempt_id,
            extra={'assignment_id': str(assignment.assignment_id), 'status': assignment.status},
        )
        due_count += 1
    for assignment in queryset.filter(status=constants.RETEST_DUE, grace_until__lte=now):
        assignment.status = constants.RETEST_MISSED
        assignment.save(update_fields=['status', 'updated_at'])
        events.emit_event(
            user=assignment.student,
            event_type='retest_assign',
            event_id=f'm6-retest-missed-{assignment.assignment_id}',
            catalog=assignment.catalog,
            task=assignment.selected_task,
            attempt_id=assignment.original_attempt.attempt_id,
            extra={
                'assignment_id': str(assignment.assignment_id),
                'status': assignment.status,
                'note': '未参加或到期未完成，不记为知识错误。',
            },
        )
        missed_count += 1
    return {'due': due_count, 'missed': missed_count}


@transaction.atomic
def claim_retest(assignment, student):
    if assignment.student_id != student.id:
        raise PermissionError('复测安排不属于该学生。')
    if assignment.status == constants.RETEST_PENDING_ITEM:
        raise ValueError('复测题池暂无可用新场景，请等待课程补题。')
    if assignment.status in (constants.RETEST_COMPLETED, constants.RETEST_MISSED, constants.RETEST_WAIVED):
        raise ValueError('该复测安排已结束。')
    if assignment.selected_task is None:
        raise ValueError('复测任务尚未确定。')
    if assignment.started_attempt_id:
        existing = assignment.started_attempt
        if existing and existing.status not in ('verified', 'abandoned'):
            return existing, False

    from learning_map.models import TaskAttempt

    attempt = TaskAttempt.objects.create(
        student=student,
        catalog=assignment.catalog,
        task=assignment.selected_task,
        task_version=assignment.selected_task.version,
        capability_ids=sorted(
            assignment.selected_task.capabilities.values_list('stable_id', flat=True)
        ),
        status='claimed',
    )
    assignment.started_attempt = attempt
    assignment.status = constants.RETEST_IN_PROGRESS
    assignment.save(update_fields=['started_attempt', 'status', 'updated_at'])
    events.emit_event(
        user=student,
        event_type='task_claim',
        event_id=f'm6-retest-claim-{attempt.attempt_id}',
        catalog=assignment.catalog,
        task=assignment.selected_task,
        attempt_id=attempt.attempt_id,
        capability_ids=attempt.capability_ids,
        extra={
            'assignment_id': str(assignment.assignment_id),
            'retest': True,
            'original_attempt_id': str(assignment.original_attempt.attempt_id),
        },
    )
    return attempt, True
