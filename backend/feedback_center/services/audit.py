"""Append-only action and review helpers shared by submission and workflow."""

from django.utils import timezone

from .. import constants
from ..models import FeedbackAction, FeedbackReview
from .events import create_event_link


def role_of(user):
    return getattr(user, 'role', '') or 'unknown'


def record_action(ticket, *, action, actor, from_status, to_status, reason='',
                  metadata=None, visibility=constants.VISIBILITY_STUDENT,
                  event_type=''):
    row = FeedbackAction.objects.create(
        ticket=ticket,
        action=action,
        from_status=from_status or '',
        to_status=to_status or '',
        event_type=event_type or '',
        actor=actor,
        actor_role=role_of(actor) if actor else 'system',
        reason=reason or '',
        metadata=metadata or {},
        visibility=visibility,
        ticket_version=ticket.version,
    )
    link = create_event_link(ticket, action=row, event_type=event_type) if event_type else None
    return row, link


def create_review(ticket, *, conclusion, reason, evidence_refs, reviewer):
    previous = FeedbackReview.objects.filter(ticket=ticket, is_current=True).first()
    if previous is not None:
        FeedbackReview.objects.filter(pk=previous.pk).update(is_current=False)
    review = FeedbackReview.objects.create(
        ticket=ticket,
        conclusion=conclusion,
        reason=reason,
        evidence_refs=evidence_refs or [],
        reviewer=reviewer,
        reviewer_role=role_of(reviewer),
        original_decision_snapshot={
            'ref': ticket.original_decision_ref,
            'version': ticket.original_decision_version,
            'snapshot': ticket.original_decision_snapshot,
            'ticket_version': ticket.version,
        },
        supersedes=previous,
        is_current=True,
        ticket_version=ticket.version + 1,
    )
    return review


def touch_version(ticket):
    ticket.version += 1
    return ticket.version


def now():
    return timezone.now()
