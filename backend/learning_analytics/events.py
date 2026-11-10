import logging

from .models import LearningBehaviorEvent


logger = logging.getLogger(__name__)


def record_learning_event(student, event_type, metadata=None):
    if not student or not getattr(student, 'is_authenticated', False):
        return None
    try:
        return LearningBehaviorEvent.objects.create(
            student=student,
            event_type=event_type,
            metadata=metadata or {},
        )
    except Exception:
        logger.exception('Unable to record learning behavior event.')
        return None
