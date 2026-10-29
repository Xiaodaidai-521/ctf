"""Submission snapshots, assistance accounting and independence.

The first effective submission for an attempt is frozen for statistics.  Later
resubmissions are preserved but never replace that first effective attempt.
Assistance only counts when it was actually shown before the submission time.
"""

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from . import events, verification
from .. import constants
from ..models import AssistanceRecord, SubmissionSnapshot


class SubmissionError(ValueError):
    code = 'invalid_submission'


class SubmissionConflict(SubmissionError):
    code = 'submission_conflict'


def payload_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def assistance_snapshot(*, attempt, before, tracking=constants.ASSISTANCE_TRACKING_COMPLETE):
    records = AssistanceRecord.objects.filter(
        attempt=attempt,
        shown=True,
        shown_at__lte=before,
    ).order_by('shown_at', 'created_at')
    effective = [
        record for record in records
        if record.kind in (constants.ASSISTANCE_KIND_HINT, constants.ASSISTANCE_KIND_TEACHER_HELP)
    ]
    requested_not_shown = AssistanceRecord.objects.filter(
        attempt=attempt,
        kind=constants.ASSISTANCE_KIND_HINT,
        shown=False,
        requested_at__lte=before,
    ).count()
    exposure = AssistanceRecord.objects.filter(
        student=attempt.student,
        task=attempt.task,
        kind=constants.ASSISTANCE_KIND_ANALYSIS_VIEW,
        shown_at__lte=before,
    ).exists()

    level = max([record.level for record in effective] or [0])
    source = (
        effective[-1].source if effective
        else constants.ASSISTANCE_SOURCE_NONE
    )
    if tracking == constants.ASSISTANCE_TRACKING_MISSING:
        independence = constants.INDEPENDENCE_UNKNOWN
        reason = 'help_record_missing'
    elif exposure:
        independence = constants.INDEPENDENCE_UNKNOWN
        reason = 'answer_exposure'
    elif effective:
        independence = constants.INDEPENDENCE_ASSISTED
        reason = 'help_shown'
    else:
        independence = constants.INDEPENDENCE_INDEPENDENT
        reason = 'no_help_shown'

    return {
        'independence': independence,
        'reason': reason,
        'level': level,
        'source': source,
        'shown': bool(effective),
        'help_records': [
            {
                'record_id': str(record.record_id),
                'kind': record.kind,
                'level': record.level,
                'source': record.source,
                'shown_at': record.shown_at.isoformat() if record.shown_at else None,
            }
            for record in effective
        ],
        'requested_not_shown': requested_not_shown,
        'answer_exposure': exposure,
    }


@transaction.atomic
def create_submission(
    *,
    student,
    attempt,
    client_submission_id,
    payload,
    assistance_tracking=constants.ASSISTANCE_TRACKING_COMPLETE,
    now=None,
    data_lab_evidence=None,
):
    now = now or timezone.now()
    if attempt.task.validator.get('type') == 'data_lab':
        from data_lab.verification import validate_context
        validate_context(data_lab_evidence, student, attempt, payload)
    if attempt.student_id != student.id:
        raise PermissionError('尝试不属于该学生。')
    if attempt.status in ('abandoned',):
        raise SubmissionError('该尝试已放弃。')
    if attempt.task.status != 'frozen':
        raise SubmissionError('任务尚未冻结，不能提交。')
    if attempt.task.version != attempt.task_version:
        raise SubmissionError('任务版本已变化，请教师安排新的尝试。')
    if not isinstance(payload, dict):
        raise SubmissionError('提交内容必须是 JSON 对象。')

    digest = payload_hash(payload)
    existing = SubmissionSnapshot.objects.filter(
        student=student, client_submission_id=client_submission_id,
    ).first()
    if existing:
        if existing.payload_hash != digest:
            raise SubmissionConflict('相同提交标识对应不同内容，请使用新的提交标识。')
        return existing, False

    sequence = (
        SubmissionSnapshot.objects.filter(attempt=attempt).count() + 1
    )
    first_effective = not SubmissionSnapshot.objects.filter(
        attempt=attempt, first_effective=True,
    ).exists()
    assistance = assistance_snapshot(
        attempt=attempt, before=now, tracking=assistance_tracking,
    )
    submission = SubmissionSnapshot.objects.create(
        client_submission_id=client_submission_id,
        attempt=attempt,
        student=student,
        task=attempt.task,
        catalog=attempt.catalog,
        task_version=attempt.task_version,
        sequence=sequence,
        payload=payload,
        payload_hash=digest,
        assistance_tracking=assistance_tracking,
        assistance_snapshot=assistance,
        independence=assistance['independence'],
        answer_exposure=assistance['answer_exposure'],
        first_effective=first_effective,
        created_at=now,
    )
    attempt.status = 'pending_verification'
    attempt.submitted_at = now
    attempt.submission_snapshot = {
        'submission_id': str(submission.submission_id),
        'payload_hash': digest,
        'sequence': sequence,
    }
    attempt.save(update_fields=['status', 'submitted_at', 'submission_snapshot'])

    events.emit_event(
        user=student,
        event_type='task_submit',
        event_id=f'm6-submit-{submission.submission_id}',
        catalog=submission.catalog,
        task=submission.task,
        attempt_id=attempt.attempt_id,
        submission_id=submission.submission_id,
        capability_ids=[
            capability.stable_id for capability in submission.task.capabilities.all()
        ],
        extra={
            'submission_hash': digest,
            'sequence': sequence,
            'first_effective': first_effective,
            'independence': submission.independence,
            'assistance_level': assistance['level'],
            'assistance_shown': assistance['shown'],
            'assistance_tracking': assistance_tracking,
            'payload_keys': sorted(payload.keys()),
        },
    )
    result = verification.create_result_for_submission(submission, now=now, data_lab_evidence=data_lab_evidence)
    return submission, True


def request_hint(*, student, attempt, level, source, content_ref='', actor=None):
    if level not in constants.HINT_LEVELS:
        raise ValueError('提示层级必须是 1—4。')
    if source not in (constants.ASSISTANCE_SOURCE_AI, constants.ASSISTANCE_SOURCE_CARD):
        raise ValueError('提示来源必须是 AI 或预置卡片。')
    if attempt.student_id != student.id:
        raise PermissionError('尝试不属于该学生。')
    now = timezone.now()
    record = AssistanceRecord.objects.create(
        event_id=f'm6-hint-request-{attempt.attempt_id}-{level}-{now.timestamp()}',
        student=student,
        attempt=attempt,
        task=attempt.task,
        capability=attempt.task.capabilities.order_by('course_order', 'stable_id').first(),
        kind=constants.ASSISTANCE_KIND_HINT,
        level=level,
        source=source,
        requested_at=now,
        shown=False,
        content_ref=content_ref,
        created_by=actor or student,
    )
    events.emit_event(
        user=student,
        event_type='hint_request',
        event_id=record.event_id,
        catalog=attempt.catalog,
        task=attempt.task,
        attempt_id=attempt.attempt_id,
        capability_ids=[record.capability.stable_id] if record.capability else [],
        extra={'level': level, 'source': source, 'shown': False},
    )
    return record


def show_hint(*, record, actor=None, now=None):
    now = now or timezone.now()
    if record.shown:
        return record, False
    record.shown = True
    record.shown_at = now
    record.save(update_fields=['shown', 'shown_at'])
    events.emit_event(
        user=record.student,
        event_type='hint_show',
        event_id=f'{record.event_id}-shown',
        catalog=record.attempt.catalog,
        task=record.task,
        attempt_id=record.attempt.attempt_id,
        capability_ids=[record.capability.stable_id] if record.capability else [],
        assistance_level=record.level,
        assistance_source=record.source,
        assistance_shown=True,
        extra={'level': record.level, 'source': record.source, 'shown': True},
    )
    return record, True


def record_teacher_help(*, teacher, attempt, summary, actor=None):
    now = timezone.now()
    record = AssistanceRecord.objects.create(
        event_id=f'm6-teacher-help-{attempt.attempt_id}-{now.timestamp()}',
        student=attempt.student,
        attempt=attempt,
        task=attempt.task,
        capability=attempt.task.capabilities.order_by('course_order', 'stable_id').first(),
        kind=constants.ASSISTANCE_KIND_TEACHER_HELP,
        level=0,
        source=constants.ASSISTANCE_SOURCE_TEACHER,
        requested_at=now,
        shown_at=now,
        shown=True,
        note=summary,
        created_by=teacher,
    )
    events.emit_event(
        user=attempt.student,
        event_type='teacher_help',
        event_id=record.event_id,
        catalog=attempt.catalog,
        task=attempt.task,
        attempt_id=attempt.attempt_id,
        capability_ids=[record.capability.stable_id] if record.capability else [],
        assistance_source=constants.ASSISTANCE_SOURCE_TEACHER,
        assistance_shown=True,
        extra={'teacher_id': teacher.id, 'summary': summary[:200]},
    )
    return record


def record_analysis_view(*, student, task, attempt=None, content_ref='', actor=None):
    now = timezone.now()
    record = AssistanceRecord.objects.create(
        event_id=f'm6-analysis-{student.id}-{task.id}-{now.timestamp()}',
        student=student,
        attempt=attempt or task.attempts.filter(student=student).order_by('-claimed_at').first(),
        task=task,
        capability=task.capabilities.order_by('course_order', 'stable_id').first(),
        kind=constants.ASSISTANCE_KIND_ANALYSIS_VIEW,
        level=0,
        source=constants.ASSISTANCE_SOURCE_CARD,
        requested_at=now,
        shown_at=now,
        shown=True,
        content_ref=content_ref,
        created_by=actor or student,
    )
    events.emit_event(
        user=student,
        event_type='analysis_view',
        event_id=record.event_id,
        catalog=task.catalog,
        task=task,
        attempt_id=record.attempt.attempt_id if record.attempt else None,
        extra={'content_ref': content_ref},
    )
    return record
