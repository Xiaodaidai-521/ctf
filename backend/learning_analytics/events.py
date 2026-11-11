import json
import logging

from django.db import IntegrityError, transaction

from .models import LearningBehaviorEvent


logger = logging.getLogger(__name__)


class LearningEventConflict(ValueError):
    pass


def _canonical(value):
    return json.dumps(value or {}, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)


def _matching_event(event, student, event_type, metadata):
    if (event.student_id != student.pk or event.event_type != event_type
            or _canonical(event.metadata) != _canonical(metadata)):
        raise LearningEventConflict('The event ID already exists with different content.')
    return event


def record_learning_event(student, event_type, metadata=None, *, event_id=None, strict=False):
    """Keep legacy best-effort writes and support strict, idempotent teaching events."""
    if not student or not getattr(student, 'is_authenticated', False):
        if strict:
            raise ValueError('An authenticated student is required.')
        return None
    if event_id is not None:
        event_id = str(event_id)
        if len(event_id) > 64:
            raise ValueError('event_id must not exceed 64 characters.')
        # Missing IDs remain independent legacy events, rather than one unique ''.
        event_id = event_id or None
    event_metadata = metadata or {}
    try:
        with transaction.atomic():
            if event_id:
                existing = LearningBehaviorEvent.objects.filter(event_id=event_id).first()
                if existing:
                    return _matching_event(existing, student, event_type, event_metadata)
            try:
                # The savepoint must roll back before querying a concurrent insert.
                with transaction.atomic():
                    return LearningBehaviorEvent.objects.create(
                        event_id=event_id,
                        student=student,
                        event_type=event_type,
                        metadata=event_metadata,
                    )
            except IntegrityError:
                if not event_id:
                    raise
                existing = LearningBehaviorEvent.objects.filter(event_id=event_id).first()
                if existing is None:
                    raise
                return _matching_event(existing, student, event_type, event_metadata)
    except LearningEventConflict:
        raise
    except Exception:
        if strict:
            raise
        logger.exception('Unable to record learning behavior event.')
        return None
