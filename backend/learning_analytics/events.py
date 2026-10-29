import json
import logging

from django.db import IntegrityError, transaction

from .models import LearningBehaviorEvent


logger = logging.getLogger(__name__)


class LearningEventConflict(ValueError):
    pass


def _canonical(value):
    return json.dumps(value or {}, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)


def record_learning_event(student, event_type, metadata=None, *, event_id=None, strict=False):
    """Write through the existing behavior-event entry point.

    Legacy callers retain best-effort behavior when ``strict`` is false. Module
    two supplies a bounded event ID and uses strict mode so failed writes cannot
    be reported as success.
    """
    if not student or not getattr(student, 'is_authenticated', False):
        if strict:
            raise ValueError('An authenticated student is required.')
        return None
    if event_id is not None and len(str(event_id)) > 64:
        raise ValueError('event_id must not exceed 64 characters.')

    event_metadata = metadata or {}
    try:
        with transaction.atomic():
            if event_id:
                existing = LearningBehaviorEvent.objects.filter(event_id=event_id).first()
                if existing:
                    if (
                        existing.student_id != student.id
                        or existing.event_type != event_type
                        or _canonical(existing.metadata) != _canonical(event_metadata)
                    ):
                        raise LearningEventConflict('The event ID already exists with different content.')
                    return existing
            try:
                return LearningBehaviorEvent.objects.create(
                    event_id=event_id,
                    student=student,
                    event_type=event_type,
                    metadata=event_metadata,
                )
            except IntegrityError:
                if not event_id:
                    raise
                existing = LearningBehaviorEvent.objects.get(event_id=event_id)
                if (
                    existing.student_id != student.id
                    or existing.event_type != event_type
                    or _canonical(existing.metadata) != _canonical(event_metadata)
                ):
                    raise LearningEventConflict('The event ID already exists with different content.')
                return existing
    except LearningEventConflict:
        raise
    except Exception:
        if strict:
            raise
        logger.exception('Unable to record learning behavior event.')
        return None
