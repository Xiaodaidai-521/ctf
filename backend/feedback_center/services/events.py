"""Shared-event outbox for module 7.

Every status-changing action gets one deterministic ``LearningEvent`` ID.  The
event row is written after the business transaction commits; if that write
fails, the feedback ticket remains saved and the outbox row stays ``pending``
for the teacher reconciliation page.  Retrying the same row cannot create a
second event, and an event whose metadata belongs to another feedback is shown
as ``mismatch`` instead of being overwritten.
"""

from django.utils import timezone

from learning_analytics.models import LearningEvent
from learning_map.services.events import emit_event

from .. import constants
from ..models import FeedbackEventLink


def event_id_for(ticket, action=None):
    if action is not None:
        return f'fb-action-{action.action_id}'
    return f'fb-submit-{ticket.feedback_id}'


def create_event_link(ticket, *, action=None, event_type=None):
    event_type = event_type or (action.event_type if action else constants.EVENT_FEEDBACK_SUBMITTED)
    if not event_type:
        return None
    link, _ = FeedbackEventLink.objects.get_or_create(
        event_id=event_id_for(ticket, action),
        defaults={
            'ticket': ticket,
            'action': action,
            'event_type': event_type,
            'status': constants.EVENT_LINK_PENDING,
        },
    )
    return link


def _event_metadata(ticket):
    return {
        'source': 'feedback_center',
        'feedback_id': str(ticket.feedback_id),
        'feedback_category': ticket.category,
        'feedback_issue_type': ticket.issue_type,
        'feedback_status': ticket.status,
        'feedback_ticket_version': ticket.version,
        'duplicate_of': str(ticket.duplicate_of.feedback_id) if ticket.duplicate_of else '',
    }


def _metadata_matches(event, link):
    metadata = event.metadata or {}
    if event.event_type != link.event_type:
        return False
    if metadata.get('feedback_id') != str(link.ticket.feedback_id):
        return False
    if link.action_id and metadata.get('feedback_action_id') != str(link.action.action_id):
        return False
    return True


def sync_event_link(link):
    """Attempt to link one outbox row to the canonical event store.

    Returns the resulting status string.  Never raises for a transport/DB
    failure; the caller shows the pending state instead of claiming success.
    """

    link = FeedbackEventLink.objects.select_related('ticket', 'action').get(pk=link.pk)
    ticket = link.ticket
    link.attempts += 1
    link.checked_at = timezone.now()

    existing = LearningEvent.objects.filter(event_id=link.event_id).first()
    if existing is not None:
        if _metadata_matches(existing, link):
            link.status = constants.EVENT_LINK_LINKED
            link.last_error = ''
        else:
            link.status = constants.EVENT_LINK_MISMATCH
            link.last_error = 'metadata_mismatch'
        link.save(update_fields=['status', 'last_error', 'attempts', 'checked_at'])
        return link.status

    try:
        metadata = _event_metadata(ticket)
        if link.action:
            metadata['feedback_status'] = link.action.to_status or ticket.status
            metadata['feedback_ticket_version'] = link.action.ticket_version
        metadata.update({
            'feedback_action': link.action.action if link.action else 'submit',
            'feedback_action_id': str(link.action.action_id) if link.action else '',
        })
        emit_event(
            user=ticket.student,
            event_type=link.event_type,
            event_id=link.event_id,
            catalog=ticket.catalog,
            task=ticket.task,
            attempt_id=ticket.attempt_id,
            capability_ids=[ticket.capability.stable_id] if ticket.capability_id else [],
            knowledge_point_ids=[ticket.knowledge_point.stable_id] if ticket.knowledge_point_id else [],
            evidence_ref=f'feedback:{ticket.feedback_id}',
            extra=metadata,
        )
    except Exception as exc:  # noqa: BLE001 - only a type name is retained
        link.status = constants.EVENT_LINK_PENDING
        link.last_error = type(exc).__name__
        link.save(update_fields=['status', 'last_error', 'attempts', 'checked_at'])
        return link.status

    link.status = constants.EVENT_LINK_LINKED
    link.last_error = ''
    link.save(update_fields=['status', 'last_error', 'attempts', 'checked_at'])
    return link.status


def sync_links(links):
    statuses = []
    for link in links:
        if link is None:
            continue
        statuses.append(sync_event_link(link))
    if not statuses:
        return {'linked': 0, 'pending': 0, 'mismatch': 0, 'status': 'linked'}
    linked = statuses.count(constants.EVENT_LINK_LINKED)
    pending = statuses.count(constants.EVENT_LINK_PENDING)
    mismatch = statuses.count(constants.EVENT_LINK_MISMATCH)
    if pending and (linked or mismatch):
        state = 'partial'
    elif pending:
        state = 'pending_retry'
    elif mismatch:
        state = 'mismatch'
    else:
        state = 'linked'
    return {'linked': linked, 'pending': pending, 'mismatch': mismatch, 'status': state}


def ensure_action_links(ticket):
    """Repair missing outbox rows for actions that should have an event."""

    created = []
    for action in ticket.actions.exclude(event_type='').order_by('created_at'):
        if not FeedbackEventLink.objects.filter(action=action).exists():
            link = create_event_link(ticket, action=action, event_type=action.event_type)
            if link:
                created.append(link)
    return created


def retry_pending(*, ticket=None, limit=100):
    queryset = FeedbackEventLink.objects.filter(
        status__in=(constants.EVENT_LINK_PENDING,),
    ).select_related('ticket', 'action').order_by('created_at')
    if ticket is not None:
        queryset = queryset.filter(ticket=ticket)
    links = list(queryset[:limit])
    result = sync_links(links)
    result['attempted'] = len(links)
    return result


def link_payload(link):
    return {
        'event_id': link.event_id,
        'event_type': link.event_type,
        'status': link.status,
        'status_label': constants.EVENT_LINK_STATUS_LABELS.get(link.status, link.status),
        'attempts': link.attempts,
        'last_error': link.last_error,
        'checked_at': link.checked_at.isoformat() if link.checked_at else None,
        'action_id': str(link.action.action_id) if link.action else '',
        'action': link.action.action if link.action else 'submit',
    }
