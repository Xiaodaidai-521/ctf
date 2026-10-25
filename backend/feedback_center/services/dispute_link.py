"""Module 6 <-> module 7 dispute synchronisation.

Module 7 never changes a score.  When a teaching/scoring feedback is confirmed
as a score dispute, module 7 asks module 6 to open a ``ScoreDispute`` and then
mirrors its status for reconciliation.  Module 6 remains the owner of the
dispute; module 7 only records that it referred it.
"""

from django.db import transaction
from django.utils import timezone

from skill_review.models import ScoreDispute
from skill_review.services import disputes as dispute_service

from .. import constants
from ..models import FeedbackModule6DisputeLink, FeedbackTicket


class DisputeLinkError(ValueError):
    code = 'dispute_link_invalid'


def _current_submission(ticket):
    from skill_review.models import SubmissionSnapshot

    if ticket.attempt_id is None:
        return None
    return (
        SubmissionSnapshot.objects.filter(attempt_id=ticket.attempt_id)
        .order_by('-created_at').first()
    )


@transaction.atomic
def open_dispute_for_ticket(ticket, *, actor):
    if ticket.category != constants.CATEGORY_TEACHING:
        raise DisputeLinkError('只有教学类反馈可以转交评分争议。')
    if ticket.issue_type != 'scoring_dispute':
        raise DisputeLinkError('只有“评分争议”类型可以转交模块六。')
    if ticket.status not in constants.CANDIDATE_SOURCE_STATUSES:
        raise DisputeLinkError('反馈尚未完成事实确认，不能转交评分争议。')
    if FeedbackModule6DisputeLink.objects.filter(ticket=ticket).exists():
        return FeedbackModule6DisputeLink.objects.get(ticket=ticket), False

    submission = _current_submission(ticket)
    if submission is None:
        raise DisputeLinkError('该反馈没有关联到已提交的尝试，无法建立评分争议。')

    dispute, _created = dispute_service.create_dispute(
        student=ticket.student,
        submission=submission,
        client_dispute_id=f'feedback-{ticket.feedback_id}',
        reason=f'{ticket.dispute}\n\n（由反馈工单 {ticket.feedback_id} 转交）',
    )
    link = FeedbackModule6DisputeLink.objects.create(
        ticket=ticket,
        dispute_id=dispute.dispute_id,
        submission_id=submission.submission_id,
        status_snapshot=dispute.status,
        resolution_snapshot=dispute.resolution,
        synced_at=timezone.now(),
        created_by=actor,
    )
    return link, True


def sync_dispute_status(link):
    """Pull the module-6 dispute status back onto the link."""

    dispute = ScoreDispute.objects.filter(dispute_id=link.dispute_id).first()
    if dispute is None:
        return link, False
    changed = (
        dispute.status != link.status_snapshot
        or (dispute.resolution or '') != (link.resolution_snapshot or '')
    )
    if changed:
        link.status_snapshot = dispute.status
        link.resolution_snapshot = dispute.resolution
        link.synced_at = timezone.now()
        link.save(update_fields=['status_snapshot', 'resolution_snapshot', 'synced_at'])
    return link, changed


def link_payload(link):
    return {
        'ticket_id': str(link.ticket_id),
        'dispute_id': str(link.dispute_id),
        'submission_id': str(link.submission_id) if link.submission_id else None,
        'status': link.status_snapshot,
        'status_label': dict(constants.DISPUTE_STATUS_MIRROR_LABELS).get(
            link.status_snapshot, link.status_snapshot,
        ),
        'resolution': link.resolution_snapshot,
        'synced_at': link.synced_at.isoformat() if link.synced_at else None,
        'note': '模块六持有争议结论；模块七只镜像状态，不修改成绩。',
    }
