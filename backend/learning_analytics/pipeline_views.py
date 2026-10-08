from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from learning_paths.models import KnowledgeConcept, LearningPath, PathModule
from users.models import CTFUser

from .models import DailyLearningStat, LearningEffectSnapshot, LearningEvent, LearningRecommendation
from .services import ALGORITHM_VERSION

MAX_BATCH_SIZE = 100
METADATA_FIELDS = {'success', 'score', 'playback_rate', 'position', 'answer_duration_seconds', 'attempt_count', 'source'}
DIMENSION_KEYS = ('time_score', 'completion_score', 'mastery_score', 'retention_score', 'consistency_score', 'efficiency_score', 'engagement_score', 'focus_score')


def can_access_student(actor, student):
    if actor.role == 'student':
        return actor.id == student.id
    return actor.role in {'teacher', 'admin'} or actor.is_staff


def get_student(request, student_id=None):
    requested_id = student_id or request.query_params.get('student_id')
    if not requested_id:
        return request.user if request.user.role == 'student' else None
    try:
        student = CTFUser.objects.get(id=int(requested_id), role='student')
    except (CTFUser.DoesNotExist, TypeError, ValueError):
        return None
    return student if can_access_student(request.user, student) else None


class LearningEventBatchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        events = request.data.get('events')
        if not isinstance(events, list) or not events:
            return Response({'code': 'invalid_events', 'detail': 'events must be a non-empty list'}, status=status.HTTP_400_BAD_REQUEST)
        if len(events) > MAX_BATCH_SIZE:
            return Response({'code': 'batch_too_large', 'detail': f'events cannot exceed {MAX_BATCH_SIZE}'}, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        results, objects, seen_ids = [], [], set()
        for index, payload in enumerate(events):
            event_id = str(payload.get('eventId', '')).strip()
            event_type = str(payload.get('eventType', '')).strip()
            event_time = parse_datetime(str(payload.get('eventTime', '')))
            if not event_id or event_type not in dict(LearningEvent.EVENT_TYPES) or event_time is None:
                results.append({'index': index, 'status': 'rejected', 'code': 'invalid_event'})
                continue
            if event_id in seen_ids or LearningEvent.objects.filter(event_id=event_id).exists():
                results.append({'index': index, 'event_id': event_id, 'status': 'duplicate'})
                continue
            if timezone.is_naive(event_time):
                event_time = timezone.make_aware(event_time, timezone.get_current_timezone())
            if event_time > now + timedelta(minutes=5) or event_time < now - timedelta(days=365):
                results.append({'index': index, 'status': 'rejected', 'code': 'invalid_event_time'})
                continue
            metadata = payload.get('metadata') or {}
            try:
                duration_ms = int(payload.get('durationMs', 0) or 0)
            except (TypeError, ValueError):
                results.append({'index': index, 'status': 'rejected', 'code': 'invalid_duration'})
                continue
            if not isinstance(metadata, dict) or set(metadata) - METADATA_FIELDS or len(str(metadata)) > 4096:
                results.append({'index': index, 'status': 'rejected', 'code': 'invalid_metadata'})
                continue
            course = LearningPath.objects.filter(id=payload.get('courseId')).first() if payload.get('courseId') else None
            lesson = PathModule.objects.filter(id=payload.get('lessonId')).first() if payload.get('lessonId') else None
            knowledge_point = KnowledgeConcept.objects.filter(id=payload.get('knowledgePointId')).first() if payload.get('knowledgePointId') else None
            objects.append(LearningEvent(event_id=event_id, user=request.user, course=course, lesson=lesson, knowledge_point=knowledge_point, event_type=event_type, event_time=event_time, device_id=str(payload.get('deviceId', ''))[:128], device_type=str(payload.get('deviceType', ''))[:32], client_session_id=str(payload.get('clientSessionId', ''))[:128], page_visible=bool(payload.get('pageVisible', True)), duration_ms=max(0, min(duration_ms, 1800000)), progress=payload.get('progress'), metadata=metadata))
            seen_ids.add(event_id)
            results.append({'index': index, 'event_id': event_id, 'status': 'accepted'})
        LearningEvent.objects.bulk_create(objects, ignore_conflicts=True)
        return Response({'results': results, 'accepted_count': len(objects), 'rejected_count': sum(item['status'] == 'rejected' for item in results)})


class LearningEffectSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = get_student(request)
        if not student:
            return Response({'detail': 'A permitted student_id is required.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            days = int(request.query_params.get('days', 30))
        except (TypeError, ValueError):
            return Response({'detail': 'days must be 7, 30, or 90.'}, status=status.HTTP_400_BAD_REQUEST)
        if days not in {7, 30, 90}:
            return Response({'detail': 'days must be 7, 30, or 90.'}, status=status.HTTP_400_BAD_REQUEST)
        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=days - 1)
        snapshots = LearningEffectSnapshot.objects.filter(user=student, analysis_start_date=start_date, analysis_end_date=end_date, algorithm_version=ALGORITHM_VERSION).order_by('-calculated_at')
        snapshot = snapshots.first()
        if not snapshot:
            return Response({'student': {'id': student.id, 'username': student.username}, 'period': {'days': days, 'start_date': start_date, 'end_date': end_date}, 'snapshot': None, 'daily_stats': [], 'recommendations': [], 'message': 'Analytics snapshot is not available yet.'})
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=days - 1)
        previous = LearningEffectSnapshot.objects.filter(user=student, analysis_start_date=previous_start, analysis_end_date=previous_end, algorithm_version=ALGORITHM_VERSION).first()
        daily = DailyLearningStat.objects.filter(user=student, stat_date__gte=start_date, stat_date__lte=end_date, algorithm_version=ALGORITHM_VERSION).order_by('stat_date')
        recommendations = LearningRecommendation.objects.filter(user=student, status='active', algorithm_version=ALGORITHM_VERSION).order_by('priority', '-generated_at')[:5]
        snapshot_payload = {'total_effect_score': snapshot.total_effect_score, 'effect_level': snapshot.effect_level, 'confidence_score': snapshot.confidence_score, 'dimensions': {key: getattr(snapshot, key) for key in DIMENSION_KEYS}, 'sample_description': snapshot.sample_description, 'calculated_at': snapshot.calculated_at}
        previous_payload = {'dimensions': {key: getattr(previous, key) for key in DIMENSION_KEYS}, 'sample_description': previous.sample_description} if previous else None
        return Response({'student': {'id': student.id, 'username': student.username}, 'period': {'days': days, 'start_date': start_date, 'end_date': end_date}, 'snapshot': snapshot_payload, 'previous_snapshot': previous_payload, 'daily_stats': [{'date': item.stat_date, 'effective_learning_seconds': item.effective_learning_seconds, 'focus_score': item.focus_score, 'effect_score': item.effect_score} for item in daily], 'recommendations': [{'id': item.id, 'type': item.recommendation_type, 'priority': item.priority, 'severity': item.severity, 'title': item.title, 'content': item.content, 'reason': item.reason, 'evidence': item.evidence, 'action_text': item.action_text} for item in recommendations]})

