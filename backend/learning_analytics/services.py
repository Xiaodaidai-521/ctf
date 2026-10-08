from collections import defaultdict
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from learning_paths.models import UserKnowledgeState, UserPathProgress

from .models import DailyLearningStat, LearningEffectSnapshot, LearningEvent, LearningRecommendation, LearningSession

ALGORITHM_VERSION = 'v1'
SESSION_GAP_SECONDS = 30 * 60
READING_IDLE_SECONDS = 10 * 60
MAX_EVENT_DURATION_SECONDS = 30 * 60
MAX_DAILY_EFFECTIVE_SECONDS = 12 * 60 * 60
EVENT_DURATION_WEIGHTS = {
    'video_progress': 1.0,
    'page_heartbeat': 0.9,
    'exercise_submit': 1.2,
    'review_start': 1.3,
    'note_create': 1.1,
}
INTERACTION_TYPES = {'scroll', 'click', 'note_create', 'exercise_start', 'exercise_submit', 'answer_result'}


def clamp(value, lower=0.0, upper=100.0):
    return max(lower, min(float(value or 0), upper))


def event_duration_seconds(event):
    if not event.page_visible or event.event_type == 'page_hidden':
        return 0
    seconds = min(event.duration_ms / 1000, MAX_EVENT_DURATION_SECONDS)
    return seconds * EVENT_DURATION_WEIGHTS.get(event.event_type, 0.2)


def split_sessions(events):
    sessions, current = [], []
    previous = None
    for event in events:
        if previous is not None:
            gap = (event.event_time - previous.event_time).total_seconds()
            if gap > SESSION_GAP_SECONDS or event.event_time.date() != previous.event_time.date() or event.client_session_id != previous.client_session_id:
                sessions.append(current)
                current = []
        current.append(event)
        previous = event
    if current:
        sessions.append(current)
    return sessions


def build_sessions(user, start, end):
    events = list(LearningEvent.objects.filter(user=user, event_time__gte=start, event_time__lt=end).order_by('event_time', 'id'))
    sessions = split_sessions(events)
    LearningSession.objects.filter(user=user, start_time__gte=start, start_time__lt=end, algorithm_version=ALGORITHM_VERSION).delete()
    created = []
    for group in sessions:
        first, last = group[0], group[-1]
        raw = max(0, int((last.event_time - first.event_time).total_seconds()))
        active = sum(event_duration_seconds(event) for event in group)
        active = min(int(active), raw if raw else int(active))
        interaction_count = sum(event.event_type in INTERACTION_TYPES for event in group)
        idle = max(0, raw - active)
        abnormal = raw > 8 * 60 * 60 or active > 4 * 60 * 60
        quality = clamp((active / raw * 100) if raw else (100 if active else 0))
        session_key = sha256(f'{user.id}:{first.event_id}:{last.event_id}:{ALGORITHM_VERSION}'.encode()).hexdigest()[:64]
        created.append(LearningSession(
            session_id=session_key, user=user, course=first.course, start_time=first.event_time, end_time=last.event_time,
            raw_duration_seconds=raw, active_duration_seconds=active, effective_duration_seconds=0 if abnormal else active,
            idle_duration_seconds=idle, video_duration_seconds=int(sum(event_duration_seconds(event) for event in group if event.event_type == 'video_progress')),
            reading_duration_seconds=int(sum(event_duration_seconds(event) for event in group if event.event_type in {'content_open', 'page_heartbeat', 'scroll'})),
            practice_duration_seconds=int(sum(event_duration_seconds(event) for event in group if event.event_type in {'exercise_start', 'exercise_submit', 'answer_result'})),
            review_duration_seconds=int(sum(event_duration_seconds(event) for event in group if event.event_type == 'review_start')),
            content_count=len({event.lesson_id for event in group if event.lesson_id}), interaction_count=interaction_count,
            session_quality_score=quality, abnormal_flag=abnormal, abnormal_score=100 - quality if abnormal else 0,
            abnormal_reason='duration_limit' if abnormal else '', algorithm_version=ALGORITHM_VERSION,
        ))
    LearningSession.objects.bulk_create(created, ignore_conflicts=True)
    return created


def rebuild_daily_stats(user, start, end):
    build_sessions(user, start, end)
    sessions = LearningSession.objects.filter(user=user, start_time__gte=start, start_time__lt=end, algorithm_version=ALGORITHM_VERSION)
    by_day = defaultdict(list)
    for session in sessions:
        by_day[session.start_time.date()].append(session)
    stats = []
    for stat_date, entries in by_day.items():
        raw = sum(entry.raw_duration_seconds for entry in entries)
        active = sum(entry.active_duration_seconds for entry in entries)
        effective = min(sum(entry.effective_duration_seconds for entry in entries), MAX_DAILY_EFFECTIVE_SECONDS)
        events = LearningEvent.objects.filter(user=user, event_time__date=stat_date)
        question_count = events.filter(event_type__in=['exercise_submit', 'answer_result']).count()
        correct_count = events.filter(event_type__in=['exercise_submit', 'answer_result'], metadata__success=True).count()
        focus = clamp(active / raw * 100 if raw else 0)
        fragmentation = clamp((len(entries) - 1) / max(len(entries), 1) * 100)
        stats.append(DailyLearningStat(
            stat_date=stat_date, user=user, raw_learning_seconds=raw, active_learning_seconds=active,
            effective_learning_seconds=effective, video_learning_seconds=sum(entry.video_duration_seconds for entry in entries),
            reading_learning_seconds=sum(entry.reading_duration_seconds for entry in entries),
            practice_learning_seconds=sum(entry.practice_duration_seconds for entry in entries),
            review_learning_seconds=sum(entry.review_duration_seconds for entry in entries), session_count=len(entries),
            completed_lesson_count=events.filter(event_type='lesson_complete').count(), question_count=question_count,
            correct_question_count=correct_count, correct_rate=clamp(correct_count / question_count * 100 if question_count else 0),
            knowledge_point_count=events.exclude(knowledge_point=None).values('knowledge_point').distinct().count(),
            focus_score=focus, fragmentation_rate=fragmentation, effect_score=clamp((focus + (100 - fragmentation)) / 2), algorithm_version=ALGORITHM_VERSION,
        ))
    for stat in stats:
        DailyLearningStat.objects.update_or_create(user=user, stat_date=stat.stat_date, algorithm_version=ALGORITHM_VERSION, defaults={field.name: getattr(stat, field.name) for field in DailyLearningStat._meta.fields if field.name not in {'id', 'created_at', 'updated_at'}})
    return stats


def rebuild_effect_snapshot(user, start_date, end_date):
    stats = DailyLearningStat.objects.filter(user=user, stat_date__gte=start_date, stat_date__lte=end_date, algorithm_version=ALGORITHM_VERSION)
    aggregate = stats.aggregate(effective=Sum('effective_learning_seconds'), focus=Avg('focus_score'), efficiency=Avg('effect_score'), correct=Avg('correct_rate'), days=Count('id'))
    days = max((end_date - start_date).days + 1, 1)
    states = UserKnowledgeState.objects.filter(user=user)
    mastery = states.aggregate(value=Avg('mastery_level'))['value'] or 0
    retention = states.aggregate(value=Avg('recall_probability'))['value'] or 0
    progress = UserPathProgress.objects.filter(user=user).aggregate(value=Avg('progress_percentage'))['value'] or 0
    active_days = aggregate['days'] or 0
    time_score = clamp((aggregate['effective'] or 0) / (days * 30 * 60) * 100)
    metrics = {
        'time_score': time_score, 'completion_score': clamp(progress), 'mastery_score': clamp(mastery * 100),
        'retention_score': clamp(retention * 100), 'consistency_score': clamp(active_days / days * 100),
        'efficiency_score': clamp(aggregate['efficiency'] or 0), 'engagement_score': clamp(aggregate['correct'] or 0), 'focus_score': clamp(aggregate['focus'] or 0),
    }
    total = sum(metrics.values()) / len(metrics)
    level = 'excellent' if total >= 85 else 'good' if total >= 70 else 'developing' if total >= 50 else 'at_risk'
    confidence = clamp((active_days / min(days, 14)) * 70 + min((aggregate['effective'] or 0) / (7 * 3600), 1) * 30)
    snapshot, _ = LearningEffectSnapshot.objects.update_or_create(
        user=user, analysis_start_date=start_date, analysis_end_date=end_date, algorithm_version=ALGORITHM_VERSION,
        defaults={**metrics, 'total_effect_score': round(total, 2), 'effect_level': level, 'confidence_score': round(confidence, 2),
                  'sample_description': {'active_days': active_days, 'effective_learning_seconds': aggregate['effective'] or 0, 'data_source': 'daily_learning_stats'}},
    )
    create_recommendations(user, snapshot)
    return snapshot


def create_recommendations(user, snapshot):
    LearningRecommendation.objects.filter(user=user, status='active', algorithm_version=ALGORITHM_VERSION).update(status='expired')
    candidates = []
    if snapshot.mastery_score < 60:
        candidates.append(('mastery', 1, 'warning', '\u590d\u4e60\u8584\u5f31\u77e5\u8bc6\u70b9', '\u5efa\u8bae\u4f18\u5148\u590d\u4e60\u638c\u63e1\u5ea6\u4f4e\u4e8e 60% \u7684\u77e5\u8bc6\u70b9\u3002', {'mastery_score': snapshot.mastery_score}))
    if snapshot.consistency_score < 40:
        candidates.append(('consistency', 2, 'warning', '\u5efa\u7acb\u7a33\u5b9a\u5b66\u4e60\u8282\u594f', '\u672c\u5468\u5efa\u8bae\u5c06\u5b66\u4e60\u62c6\u5206\u5230\u66f4\u591a\u5929\u6570\u5b8c\u6210\u3002', {'consistency_score': snapshot.consistency_score}))
    if snapshot.focus_score < 50:
        candidates.append(('focus', 2, 'warning', '\u51cf\u5c11\u788e\u7247\u5316\u5b66\u4e60', '\u5efa\u8bae\u4f7f\u7528\u8fde\u7eed\u5b66\u4e60\u65f6\u6bb5\uff0c\u907f\u514d\u540e\u53f0\u64ad\u653e\u3002', {'focus_score': snapshot.focus_score}))
    if not candidates:
        if snapshot.total_effect_score >= 85:
            candidates.append(('extension', 3, 'info', '\u4fdd\u6301\u5b66\u4e60\u8282\u594f', '\u5f53\u524d\u5b66\u4e60\u8868\u73b0\u4f18\u79c0\uff0c\u5efa\u8bae\u5728\u5de9\u56fa\u6838\u5fc3\u77e5\u8bc6\u70b9\u7684\u57fa\u7840\u4e0a\u5b8c\u6210\u62d3\u5c55\u7ec3\u4e60\u3002', {'total_effect_score': snapshot.total_effect_score}))
        else:
            candidates.append(('maintenance', 3, 'info', '\u4fdd\u6301\u7a33\u5b9a\u5b66\u4e60', '\u5f53\u524d\u5404\u9879\u6307\u6807\u57fa\u672c\u7a33\u5b9a\uff0c\u5efa\u8bae\u6309\u8ba1\u5212\u5b8c\u6210\u5b66\u4e60\u4e0e\u9636\u6bb5\u590d\u76d8\u3002', {'total_effect_score': snapshot.total_effect_score}))

    for recommendation_type, priority, severity, title, content, evidence in candidates:
        LearningRecommendation.objects.create(user=user, recommendation_type=recommendation_type, priority=priority, severity=severity, title=title, content=content, reason=content, evidence=evidence, action_text='\u67e5\u770b\u5b66\u4e60\u8def\u5f84', algorithm_version=ALGORITHM_VERSION)


def rebuild_user_analytics(user, start, end):
    rebuild_daily_stats(user, start, end)
    return rebuild_effect_snapshot(user, start.date(), (end - timedelta(seconds=1)).date())


def record_event_batch(user, events):
    accepted, rejected = [], []
    now = timezone.now()
    for index, payload in enumerate(events):
        event_id = str(payload.get('eventId', '')).strip()
        event_type = payload.get('eventType')
        event_time = payload.get('eventTime')
        if not event_id or not event_type or not event_time:
            rejected.append({'index': index, 'code': 'invalid_event', 'detail': 'eventId, eventType and eventTime are required'})
            continue
        if LearningEvent.objects.filter(event_id=event_id).exists():
            accepted.append({'index': index, 'event_id': event_id, 'status': 'duplicate'})
            continue
        if event_time > now + timedelta(minutes=5) or event_time < now - timedelta(days=365):
            rejected.append({'index': index, 'code': 'invalid_event_time', 'detail': 'eventTime is outside the accepted range'})
            continue
        metadata = payload.get('metadata') or {}
        if not isinstance(metadata, dict) or len(str(metadata)) > 4096:
            rejected.append({'index': index, 'code': 'invalid_metadata', 'detail': 'metadata must be an object no larger than 4KB'})
            continue
        accepted.append({'index': index, 'event_id': event_id, 'status': 'accepted'})
    return accepted, rejected


