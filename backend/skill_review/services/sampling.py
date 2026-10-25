"""Teacher sampling batches.

Sampling is deliberately separate from the mandatory manual review queue and
from student disputes.  A pending or overdue sampling item never blocks a
result that already satisfies its required items, and it never becomes a pass
automatically.
"""

import random

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import events
from .. import constants
from ..models import (
    ResultCorrection,
    SubmissionSnapshot,
    TeacherSamplingBatch,
    TeacherSamplingItem,
    VerificationResult,
)


class SamplingError(ValueError):
    code = 'sampling_invalid'


def _current_result(submission):
    return VerificationResult.objects.filter(submission=submission, is_current=True).first()


def _high_risk_reasons(submission, result):
    reasons = []
    if submission.independence == constants.INDEPENDENCE_UNKNOWN:
        reasons.append('independence_unknown')
    if submission.assistance_snapshot.get('requested_not_shown'):
        reasons.append('help_requested_not_shown')
    if result is None:
        reasons.append('result_missing')
    else:
        if result.verification_error:
            reasons.append('verification_error')
        manual_decision = (result.manual_result or {}).get('decision')
        if result.program_status == constants.PROGRAM_PASSED and manual_decision == 'fail':
            reasons.append('program_manual_conflict')
        if result.program_status == constants.PROGRAM_FAILED and manual_decision == 'pass':
            reasons.append('program_manual_conflict')
        if result.rubric_version and result.rubric_version != settings.MODULE6_RUBRIC_VERSION:
            reasons.append('rubric_version_changed')
    if ResultCorrection.objects.filter(submission=submission).exists():
        reasons.append('has_correction')
    return reasons


def _candidate_submissions(*, catalog, window_start, window_end, task=None, capability=None):
    queryset = SubmissionSnapshot.objects.filter(
        catalog=catalog,
        first_effective=True,
        created_at__gte=window_start,
        created_at__lte=window_end,
    ).select_related('task', 'student', 'attempt')
    if task is not None:
        queryset = queryset.filter(task=task)
    if capability is not None:
        queryset = queryset.filter(task__capabilities=capability).distinct()
    return list(queryset.order_by('id'))


@transaction.atomic
def create_batch(
    *,
    actor,
    catalog,
    title,
    window_start,
    window_end,
    basis,
    deadline,
    sample_size=0,
    high_risk_size=0,
    random_seed=0,
    task=None,
    capability=None,
):
    if window_start > window_end:
        raise SamplingError('时间窗开始不能晚于结束。')
    if sample_size < 0 or high_risk_size < 0:
        raise SamplingError('样本数不能为负。')
    if not basis.strip():
        raise SamplingError('必须登记抽样依据。')

    candidates = _candidate_submissions(
        catalog=catalog, window_start=window_start, window_end=window_end,
        task=task, capability=capability,
    )
    result_map = {submission.id: _current_result(submission) for submission in candidates}
    high_risk = []
    for submission in candidates:
        reasons = _high_risk_reasons(submission, result_map.get(submission.id))
        if reasons:
            high_risk.append((submission, reasons))
    high_risk_ids = {submission.id for submission, _ in high_risk}

    rng = random.Random(random_seed)
    random_pool = [submission for submission in candidates if submission.id not in high_risk_ids]
    random_sample = rng.sample(random_pool, min(sample_size, len(random_pool)))
    high_risk_sample = rng.sample(high_risk, min(high_risk_size, len(high_risk)))

    batch = TeacherSamplingBatch.objects.create(
        title=title,
        catalog=catalog,
        task=task,
        capability=capability,
        scope={
            'window_start': window_start.isoformat(),
            'window_end': window_end.isoformat(),
            'task_key': task.task_key if task else '',
            'task_version': task.version if task else '',
            'capability_id': capability.stable_id if capability else '',
            'candidate_count': len(candidates),
            'high_risk_candidate_count': len(high_risk),
            'sampling_method': 'random_plus_high_risk',
        },
        window_start=window_start,
        window_end=window_end,
        sample_size=sample_size,
        high_risk_size=high_risk_size,
        random_seed=random_seed,
        basis=basis,
        deadline=deadline,
        status=constants.SAMPLING_OPEN,
        created_by=actor,
    )

    for submission in random_sample:
        TeacherSamplingItem.objects.create(
            batch=batch,
            submission=submission,
            result=result_map.get(submission.id),
            selection_reason=constants.SAMPLING_RANDOM,
            risk_reasons=[],
        )
    for submission, reasons in high_risk_sample:
        TeacherSamplingItem.objects.create(
            batch=batch,
            submission=submission,
            result=result_map.get(submission.id),
            selection_reason=constants.SAMPLING_HIGH_RISK,
            risk_reasons=reasons,
        )

    events.emit_event(
        user=actor,
        event_type='teacher_help',
        event_id=f'm6-sampling-batch-{batch.batch_id}',
        catalog=catalog,
        task=task,
        extra={
            'batch_id': str(batch.batch_id),
            'sample_size': sample_size,
            'high_risk_size': high_risk_size,
            'candidate_count': len(candidates),
            'random_seed': random_seed,
            'basis': basis[:200],
        },
    )
    return batch


@transaction.atomic
def claim_item(item, teacher):
    if item.batch.status != constants.SAMPLING_OPEN:
        raise SamplingError('批次已关闭。')
    if item.status == constants.SAMPLING_ITEM_CLAIMED:
        if item.claimed_by_id == teacher.id:
            return item, False
        raise SamplingError('该抽查项已被其他教师认领。')
    if item.status != constants.SAMPLING_ITEM_PENDING:
        raise SamplingError('该抽查项当前不可认领。')
    item.status = constants.SAMPLING_ITEM_CLAIMED
    item.claimed_by = teacher
    item.claimed_at = timezone.now()
    item.save(update_fields=['status', 'claimed_by', 'claimed_at', 'updated_at'])
    return item, True


@transaction.atomic
def review_item(item, *, teacher, findings, notes='', needs_correction=False, correction=None):
    if item.status not in (constants.SAMPLING_ITEM_PENDING, constants.SAMPLING_ITEM_CLAIMED):
        raise SamplingError('该抽查项当前不可复核。')
    if item.claimed_by_id and item.claimed_by_id != teacher.id:
        raise SamplingError('该抽查项已被其他教师认领。')
    required = (
        'evidence_checked', 'verifier_checked', 'rubric_checked',
        'help_checked', 'independence_checked',
    )
    missing = [key for key in required if key not in findings]
    if missing:
        raise SamplingError(f'复核记录缺少字段：{", ".join(missing)}')
    if not str(findings.get('conclusion') or '').strip():
        raise SamplingError('复核结论不能为空。')

    item.claimed_by = item.claimed_by or teacher
    item.reviewed_by = teacher
    item.reviewed_at = timezone.now()
    item.findings = findings
    item.notes = notes
    item.status = (
        constants.SAMPLING_ITEM_NEEDS_CORRECTION
        if needs_correction else constants.SAMPLING_ITEM_COMPLETED
    )
    if correction is not None:
        item.correction = correction
    item.save()
    events.emit_event(
        user=teacher,
        event_type='teacher_help',
        event_id=f'm6-sampling-review-{item.item_id}',
        catalog=item.batch.catalog,
        task=item.batch.task,
        submission_id=item.submission.submission_id,
        result_id=item.result.result_id if item.result else None,
        extra={
            'batch_id': str(item.batch.batch_id),
            'item_id': str(item.item_id),
            'selection_reason': item.selection_reason,
            'status': item.status,
            'needs_correction': needs_correction,
        },
    )
    return item


def item_is_overdue(item, now=None):
    now = now or timezone.now()
    return (
        item.batch.deadline < now
        and item.status in (constants.SAMPLING_ITEM_PENDING, constants.SAMPLING_ITEM_CLAIMED)
    )
