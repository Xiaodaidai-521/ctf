"""Error causes, review cards and retest scheduling after review."""

from django.db import transaction
from django.utils import timezone

from . import events, retest
from .. import constants
from ..models import ReviewCard, SubmissionErrorCause, SubmissionSnapshot


CARD_FIELDS = (
    'original_task_summary',
    'error_evidence',
    'judgment_at_time',
    'correct_basis',
    'next_verification',
    'student_reflection',
)
CARD_REQUIRED_FOR_COMPLETION = CARD_FIELDS


class ReviewError(ValueError):
    code = 'review_invalid'


@transaction.atomic
def upsert_review_card(*, student, submission, data, complete=False, now=None):
    if submission.student_id != student.id:
        raise PermissionError('提交不属于该学生。')
    card, _ = ReviewCard.objects.get_or_create(
        submission=submission,
        defaults={
            'student': student,
            'attempt': submission.attempt,
            'task': submission.task,
            'catalog': submission.catalog,
            'assistance_level': int(submission.assistance_snapshot.get('level') or 0),
            'assistance_source': submission.assistance_snapshot.get('source') or constants.ASSISTANCE_SOURCE_NONE,
        },
    )
    if card.status == constants.REVIEW_CARD_COMPLETED:
        raise ReviewError('复盘卡已完成，不能改写；需要重新学习请创建新尝试。')

    for field in CARD_FIELDS:
        if field in data:
            setattr(card, field, str(data.get(field) or ''))
    if not card.original_task_summary:
        card.original_task_summary = f'{submission.task.title} · {submission.task_version}'

    if complete:
        missing = [field for field in CARD_REQUIRED_FOR_COMPLETION if not getattr(card, field).strip()]
        if missing:
            raise ReviewError(f'复盘卡缺少字段：{", ".join(missing)}')
        card.status = constants.REVIEW_CARD_COMPLETED
        card.completed_at = now or timezone.now()

    card.save()
    events.emit_event(
        user=student,
        event_type='review_start' if not complete else 'review_card_complete',
        event_id=f'm6-review-card-{card.card_id}-{card.status}-{card.updated_at.timestamp()}',
        catalog=submission.catalog,
        task=submission.task,
        attempt_id=submission.attempt.attempt_id,
        submission_id=submission.submission_id,
        capability_ids=[
            capability.stable_id for capability in submission.task.capabilities.all()
        ],
        extra={
            'card_id': str(card.card_id),
            'status': card.status,
            'assistance_level': card.assistance_level,
            'assistance_source': card.assistance_source,
        },
    )
    if complete:
        assignment, _created = retest.schedule_retest(submission, now=now, actor=student)
        return card, assignment
    return card, None


@transaction.atomic
def confirm_review_card(*, card, teacher, confirmation):
    if not confirmation.strip():
        raise ReviewError('教师确认内容不能为空。')
    card.teacher_confirmation = confirmation.strip()
    card.confirmed_by = teacher
    card.confirmed_at = timezone.now()
    card.save(update_fields=[
        'teacher_confirmation', 'confirmed_by', 'confirmed_at', 'updated_at',
    ])
    events.emit_event(
        user=card.student,
        event_type='teacher_help',
        event_id=f'm6-review-confirm-{card.card_id}-{card.confirmed_at.timestamp()}',
        catalog=card.catalog,
        task=card.task,
        attempt_id=card.attempt.attempt_id,
        extra={'card_id': str(card.card_id), 'teacher_id': teacher.id},
    )
    return card


@transaction.atomic
def upsert_error_cause(*, submission, cause, status, source, actor, note=''):
    if cause not in dict(constants.ERROR_CAUSE_CHOICES):
        raise ReviewError(f'未知错因：{cause}')
    if status not in dict(constants.CAUSE_STATUS_CHOICES):
        raise ReviewError(f'未知错因状态：{status}')
    record, _ = SubmissionErrorCause.objects.update_or_create(
        submission=submission,
        cause=cause,
        defaults={
            'status': status,
            'source': source,
            'note': note,
            'confirmed_by': actor if status == constants.CAUSE_CONFIRMED else None,
        },
    )
    return record


def confirmed_causes(submission):
    return list(
        SubmissionErrorCause.objects.filter(
            submission=submission, status=constants.CAUSE_CONFIRMED,
        ).values_list('cause', flat=True)
    )
