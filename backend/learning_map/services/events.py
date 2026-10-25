"""Event helpers for module 1.

Module 1 reuses ``learning_analytics.LearningEvent`` instead of creating a
parallel event store.  The dictionary below is the module-1 subset; the same
event_id and metadata fields are what modules 6/7/8 consume.
"""

import uuid

from django.utils import timezone

from learning_analytics.models import LearningEvent


SHARED_METADATA_FIELDS = (
    'task_id',
    'task_key',
    'task_version',
    'attempt_id',
    'capability_ids',
    'knowledge_point_ids',
    'catalog_version',
    'task_purpose',
    'evidence_ref',
    'verifier_version',
    'assistance_level',
    'assistance_source',
    'assistance_shown',
    'source',
)


def new_event_id(prefix='lm'):
    return f'{prefix}-{uuid.uuid4().hex}'


def emit_event(
    *,
    user,
    event_type,
    event_id=None,
    catalog=None,
    task=None,
    attempt_id=None,
    capability_ids=None,
    knowledge_point_ids=None,
    evidence_ref='',
    verifier_version='',
    assistance_level=0,
    assistance_source='none',
    assistance_shown=False,
    extra=None,
):
    """Write one canonical learning event, idempotently by event_id.

    Returns ``(event, created)``.  A duplicate event_id returns the original
    row without touching it, which makes network retries safe.  Failures are
    not swallowed: callers that own a core state must show "保存待重试"
    instead of pretending the event was stored.
    """

    event_id = event_id or new_event_id()
    metadata = {
        'source': 'learning_map',
        'task_id': task.id if task else None,
        'task_key': task.task_key if task else '',
        'task_version': task.version if task else '',
        'attempt_id': str(attempt_id) if attempt_id else '',
        'capability_ids': list(capability_ids or []),
        'knowledge_point_ids': list(knowledge_point_ids or []),
        'catalog_version': catalog.version if catalog else '',
        'evidence_ref': evidence_ref or '',
        'verifier_version': verifier_version or '',
        'assistance_level': int(assistance_level or 0),
        'assistance_source': assistance_source or 'none',
        'assistance_shown': bool(assistance_shown),
    }
    if extra:
        metadata.update(extra)

    existing = LearningEvent.objects.filter(event_id=event_id).first()
    if existing:
        return existing, False

    event = LearningEvent.objects.create(
        event_id=event_id,
        user=user,
        event_type=event_type,
        event_time=timezone.now(),
        metadata=metadata,
    )
    return event, True


def event_summary(event):
    if event is None:
        return None
    return {
        'event_id': event.event_id,
        'event_type': event.event_type,
        'server_time': event.server_time.isoformat() if event.server_time else None,
        'metadata': event.metadata,
    }
