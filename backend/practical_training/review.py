from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from skill_review.models import ReviewCard
from skill_review.services.events import emit_event
from skill_review.services.review import CARD_REQUIRED_FOR_COMPLETION
from .models import LabAssignment


@transaction.atomic
def complete_review(*, assignment, data):
    assignment = LabAssignment.objects.select_for_update().get(pk=assignment.pk)
    evidence = assignment.evidence.filter(attempt=assignment.attempt, result__isnull=False).first()
    if not evidence:
        raise ValidationError('须先保存服务端核验结果。')
    if (set(data) != set(CARD_REQUIRED_FOR_COMPLETION)
            or any(not isinstance(value, str) or not value.strip() or len(value) > 2000 for value in data.values())):
        raise ValidationError('复盘须包含六个非空字段，每项最多 2000 字符。')
    submission = evidence.result.submission
    card, created = ReviewCard.objects.get_or_create(submission=submission, defaults={
        'student': submission.student, 'attempt': submission.attempt, 'task': submission.task,
        'catalog': submission.catalog, 'assistance_level': submission.assistance_snapshot['level'],
        'assistance_source': submission.assistance_snapshot['source'],
    })
    if card.status == 'completed':
        if any(getattr(card, key) != value for key, value in data.items()):
            raise ValidationError('已完成复盘不可覆盖。')
        return card
    for key, value in data.items():
        setattr(card, key, value)
    card.status = 'completed'
    card.completed_at = timezone.now()
    card.save()
    emit_event(user=card.student, event_type='review_card_complete', event_id=f'm5-review-{card.card_id}',
               catalog=card.catalog, task=card.task, attempt_id=card.attempt.attempt_id,
               submission_id=submission.submission_id, capability_ids=card.attempt.capability_ids,
               extra={'card_id': str(card.card_id), 'status': card.status})
    return card
