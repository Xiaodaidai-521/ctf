"""Canonical module-6 events.

Reuses ``learning_analytics.LearningEvent``; no second event store.  Answer
text is never written to an event: only identifiers, hashes and status.
"""

import uuid

from django.utils import timezone

from learning_analytics.models import LearningEvent


def new_event_id(prefix='m6'):
    return f'{prefix}-{uuid.uuid4().hex}'


def emit_event(
    *,
    user,
    event_type,
    event_id=None,
    catalog=None,
    task=None,
    attempt_id=None,
    submission_id=None,
    result_id=None,
    capability_ids=None,
    knowledge_point_ids=None,
    evidence_ref='',
    verifier_version='',
    assistance_level=0,
    assistance_source='none',
    assistance_shown=False,
    extra=None,
):
    event_id = event_id or new_event_id()
    existing = LearningEvent.objects.filter(event_id=event_id).first()
    if existing:
        return existing, False

    metadata = {
        'source': 'skill_review',
        'task_id': task.id if task else None,
        'task_key': task.task_key if task else '',
        'task_version': task.version if task else '',
        'attempt_id': str(attempt_id) if attempt_id else '',
        'submission_id': str(submission_id) if submission_id else '',
        'result_id': str(result_id) if result_id else '',
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

    event = LearningEvent.objects.create(
        event_id=event_id,
        user=user,
        event_type=event_type,
        event_time=timezone.now(),
        metadata=metadata,
    )
    return event, True
