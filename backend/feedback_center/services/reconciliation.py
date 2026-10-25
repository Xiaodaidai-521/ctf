"""Event reconciliation for module 7.

The teacher page shows whether each status-changing action has a matching
canonical ``LearningEvent``.  A missing link can be repaired from the action log;
a metadata mismatch is never overwritten automatically.
"""

from .. import constants
from ..models import FeedbackEventLink, FeedbackTicket
from .events import ensure_action_links, link_payload, retry_pending

from django.core.exceptions import ValidationError

def ticket_reconciliation(ticket):
    links_by_action = {
        link.action_id: link
        for link in ticket.event_links.select_related('action').all()
        if link.action_id
    }
    expected = []
    for action in ticket.actions.exclude(event_type='').order_by('created_at'):
        link = links_by_action.get(action.id)
        expected.append({
            'action_id': str(action.action_id),
            'action': action.action,
            'event_type': action.event_type,
            'ticket_version': action.ticket_version,
            'event_id': link.event_id if link else '',
            'status': link.status if link else constants.EVENT_LINK_MISSING,
            'status_label': constants.EVENT_LINK_STATUS_LABELS.get(
                link.status if link else constants.EVENT_LINK_MISSING,
                '事件缺失',
            ),
            'attempts': link.attempts if link else 0,
            'last_error': link.last_error if link else 'no_link',
            'checked_at': link.checked_at.isoformat() if link and link.checked_at else None,
        })
    counts = {
        constants.EVENT_LINK_LINKED: sum(1 for item in expected if item['status'] == constants.EVENT_LINK_LINKED),
        constants.EVENT_LINK_PENDING: sum(1 for item in expected if item['status'] == constants.EVENT_LINK_PENDING),
        constants.EVENT_LINK_MISMATCH: sum(1 for item in expected if item['status'] == constants.EVENT_LINK_MISMATCH),
        constants.EVENT_LINK_MISSING: sum(1 for item in expected if item['status'] == constants.EVENT_LINK_MISSING),
    }
    return {
        'feedback_id': str(ticket.feedback_id),
        'status': ticket.status,
        'status_label': constants.STATUS_LABELS.get(ticket.status, ticket.status),
        'ticket_version': ticket.version,
        'counts': counts,
        'items': expected,
        'needs_attention': any(counts[key] for key in (
            constants.EVENT_LINK_PENDING,
            constants.EVENT_LINK_MISMATCH,
            constants.EVENT_LINK_MISSING,
        )),
    }


def queue(limit=200):
    queryset = FeedbackTicket.objects.filter(
        actions__event_type__gt='',
    ).distinct().select_related('student', 'task').prefetch_related(
        'actions', 'event_links__action',
    ).order_by('-created_at')
    items = []
    totals = {
        constants.EVENT_LINK_LINKED: 0,
        constants.EVENT_LINK_PENDING: 0,
        constants.EVENT_LINK_MISMATCH: 0,
        constants.EVENT_LINK_MISSING: 0,
    }
    for ticket in queryset[:limit]:
        payload = ticket_reconciliation(ticket)
        for key in totals:
            totals[key] += payload['counts'][key]
        if payload['needs_attention']:
            items.append(payload)
    return {
        'counts': totals,
        'items': items,
        'scanned': min(limit, queryset.count()),
        'note': '仅核对反馈动作对应的统一学习事件；待重试链接可重试，内容不一致需人工核对，不自动覆盖。',
    }


def retry(actor, *, ticket_id=None, limit=100):
    if ticket_id:
        try:
            ticket = FeedbackTicket.objects.filter(feedback_id=ticket_id).first()
        except (TypeError, ValueError, ValidationError):
            ticket = None
        if not ticket:
            return {'error': 'ticket_not_found'}
        ensure_action_links(ticket)
        result = retry_pending(ticket=ticket, limit=limit)
        return {
            'ticket_id': str(ticket.feedback_id),
            'result': result,
            'reconciliation': ticket_reconciliation(ticket),
        }
    result = retry_pending(limit=limit)
    return {'result': result}


def links_payload(ticket):
    return [link_payload(link) for link in ticket.event_links.select_related('action').order_by('created_at')]
