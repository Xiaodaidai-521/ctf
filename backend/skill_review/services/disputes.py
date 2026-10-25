"""Score disputes.  Resolving a dispute never rewrites a score by itself."""

from django.db import transaction
from django.utils import timezone

from . import events
from .. import constants
from ..models import ScoreDispute


class DisputeError(ValueError):
    code = 'dispute_invalid'


@transaction.atomic
def create_dispute(*, student, submission, client_dispute_id, reason):
    if submission.student_id != student.id:
        raise PermissionError('提交不属于该学生。')
    if not reason.strip():
        raise DisputeError('争议内容不能为空。')
    existing = ScoreDispute.objects.filter(
        student=student, client_dispute_id=client_dispute_id,
    ).first()
    if existing:
        if existing.reason != reason:
            raise DisputeError('相同争议标识对应不同内容，请使用新的标识。')
        return existing, False
    dispute = ScoreDispute.objects.create(
        client_dispute_id=client_dispute_id,
        student=student,
        submission=submission,
        result=submission.results.filter(is_current=True).first(),
        reason=reason.strip(),
        status=constants.DISPUTE_SUBMITTED,
    )
    events.emit_event(
        user=student,
        event_type='answer_result',
        event_id=f'm6-dispute-{dispute.dispute_id}',
        catalog=submission.catalog,
        task=submission.task,
        attempt_id=submission.attempt.attempt_id,
        submission_id=submission.submission_id,
        extra={
            'dispute_id': str(dispute.dispute_id),
            'status': dispute.status,
            'reason_summary': reason.strip()[:200],
        },
    )
    return dispute, True


@transaction.atomic
def resolve_dispute(dispute, *, teacher, status, resolution):
    if status not in (constants.DISPUTE_RESOLVED, constants.DISPUTE_REJECTED):
        raise DisputeError('处理状态只能是 resolved 或 rejected。')
    if not resolution.strip():
        raise DisputeError('处理结论不能为空。')
    dispute.status = status
    dispute.assigned_to = dispute.assigned_to or teacher
    dispute.resolved_by = teacher
    dispute.resolved_at = timezone.now()
    dispute.resolution = resolution.strip()
    dispute.save()
    events.emit_event(
        user=dispute.student,
        event_type='teacher_help',
        event_id=f'm6-dispute-resolve-{dispute.dispute_id}-{dispute.resolved_at.timestamp()}',
        catalog=dispute.submission.catalog,
        task=dispute.submission.task,
        submission_id=dispute.submission.submission_id,
        extra={
            'dispute_id': str(dispute.dispute_id),
            'status': dispute.status,
            'teacher_id': teacher.id,
            'note': '处理争议不直接修改成绩；如需改分须另建更正版本。',
        },
    )
    return dispute
