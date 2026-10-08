from datetime import datetime, time, timedelta
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from learning_paths.models import KnowledgeConcept, LearningPath, PathModule, UserKnowledgeState, UserLearningBehavior, UserPathProgress
from users.models import CTFUser

from learning_analytics.models import LearningEvent
from learning_analytics.services import rebuild_user_analytics


SEED = 20260714
EVENT_PREFIX = 'learning-profile-20260714'
PROFILES = (
    {
        'key': 'excellent',
        'label': 'excellent',
        'current_days': 68,
        'previous_days': 52,
        'current_seconds': 3000,
        'previous_seconds': 2500,
        'success_rate': 0.92,
        'progress': 92,
        'mastery': (0.91, 0.88, 0.86),
        'recall': (0.90, 0.87, 0.84),
        'focus_gap_minutes': 24,
    },
    {
        'key': 'steady',
        'label': 'steady',
        'current_days': 46,
        'previous_days': 45,
        'current_seconds': 2050,
        'previous_seconds': 2000,
        'success_rate': 0.73,
        'progress': 72,
        'mastery': (0.72, 0.68, 0.64),
        'recall': (0.75, 0.70, 0.66),
        'focus_gap_minutes': 22,
    },
    {
        'key': 'at_risk',
        'label': 'at_risk',
        'current_days': 18,
        'previous_days': 28,
        'current_seconds': 980,
        'previous_seconds': 1450,
        'success_rate': 0.42,
        'progress': 42,
        'mastery': (0.46, 0.38, 0.32),
        'recall': (0.49, 0.43, 0.36),
        'focus_gap_minutes': 28,
    },
)


def period_bounds(days, end_date):
    start_date = end_date - timedelta(days=days - 1)
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    return start, end


def spaced_dates(start_date, end_date, count):
    available = (end_date - start_date).days + 1
    if count > available:
        raise ValueError('count exceeds available dates')
    if count == 1:
        return [end_date]
    indices = {(index * (available - 1)) // (count - 1) for index in range(count)}
    return [start_date + timedelta(days=index) for index in sorted(indices)]


class Command(BaseCommand):
    help = 'Seed deterministic learning analytics profiles for three existing students.'

    def handle(self, *args, **options):
        students = list(
            CTFUser.objects.filter(role='student')
            .exclude(username='126')
            .order_by('id')
        )
        if len(students) < 3:
            raise CommandError('At least three existing student accounts are required.')

        selected = random.Random(SEED).sample(students, 3)
        path = LearningPath.objects.order_by('id').first()
        concepts = list(KnowledgeConcept.objects.order_by('id')[:3])
        if path is None or len(concepts) < 3:
            raise CommandError('At least one learning path and three knowledge concepts are required.')

        lessons = list(PathModule.objects.filter(learning_path=path).order_by('order', 'id')[:3])
        today = timezone.localdate()
        current_start = today - timedelta(days=89)
        previous_start = current_start - timedelta(days=90)

        with transaction.atomic():
            for student, profile in zip(selected, PROFILES):
                self.seed_profile(student, profile, path, lessons, concepts, previous_start, current_start, today)
                self.rebuild_snapshots(student, today)

        for student, profile in zip(selected, PROFILES):
            self.stdout.write(
                f'{student.id}|{student.username}|{student.nickname or student.username}|'
                f'{student.class_name or "unassigned"}|{profile["label"]}'
            )

    def seed_profile(self, student, profile, path, lessons, concepts, previous_start, current_start, today):
        self.seed_progress(student, path, lessons, profile)
        self.seed_knowledge_states(student, concepts, profile)
        self.seed_period_events(
            student, profile, path, concepts, lessons,
            previous_start, current_start - timedelta(days=1),
            profile['previous_days'], profile['previous_seconds'], 'previous',
        )
        self.seed_period_events(
            student, profile, path, concepts, lessons,
            current_start, today,
            profile['current_days'], profile['current_seconds'], 'current',
        )
        self.seed_legacy_behaviors(student, profile, concepts, previous_start, current_start - timedelta(days=1), profile['previous_days'], 'previous')
        self.seed_legacy_behaviors(student, profile, concepts, current_start, today, profile['current_days'], 'current')

    def seed_progress(self, student, path, lessons, profile):
        total_modules = max(path.modules.filter(is_required=True).count(), len(lessons), 1)
        completed_modules = min(total_modules, round(total_modules * profile['progress'] / 100))
        current_module = lessons[min(completed_modules, len(lessons) - 1)] if lessons else None
        UserPathProgress.objects.update_or_create(
            user=student,
            learning_path=path,
            defaults={
                'total_modules': total_modules,
                'completed_modules': completed_modules,
                'progress_percentage': profile['progress'],
                'current_module': current_module,
                'current_position': {'source': EVENT_PREFIX, 'profile': profile['key']},
            },
        )

    def seed_knowledge_states(self, student, concepts, profile):
        now = timezone.now()
        for index, concept in enumerate(concepts):
            mastery = profile['mastery'][index]
            UserKnowledgeState.objects.update_or_create(
                user=student,
                concept=concept,
                defaults={
                    'mastery_level': mastery,
                    'times_viewed': 18 + index * 4,
                    'total_time_spent': int((index + 2) * 3600 * mastery),
                    'lab_attempts': 8 + index * 2,
                    'lab_successes': round((8 + index * 2) * mastery),
                    'last_reviewed': now - timedelta(days=index + 1),
                    'next_review_at': now + timedelta(days=3 + index * 2),
                    'recall_probability': profile['recall'][index],
                    'learning_velocity': round(mastery * 1.4, 2),
                    'struggle_indicators': {
                        'source': EVENT_PREFIX,
                        'profile': profile['key'],
                        'needs_review': profile['key'] == 'at_risk' and index > 0,
                    },
                    'recommended_intervention': 'targeted_review' if profile['key'] == 'at_risk' else 'maintain_practice',
                },
            )

    def seed_period_events(self, student, profile, path, concepts, lessons, start_date, end_date, active_days, base_seconds, segment):
        for day_index, stat_date in enumerate(spaced_dates(start_date, end_date, active_days)):
            variance = ((day_index * 17 + student.id * 7) % 19 - 9) / 100
            total_seconds = max(600, int(base_seconds * (1 + variance)))
            day_start = timezone.make_aware(datetime.combine(stat_date, time(hour=19, minute=0)))
            concept = concepts[day_index % len(concepts)]
            lesson = lessons[day_index % len(lessons)] if lessons else None
            session_id = f'{EVENT_PREFIX}-{student.id}-{segment}-{stat_date.isoformat()}'
            gap = profile['focus_gap_minutes']
            events = (
                ('content_open', 60, 0, {}),
                ('video_progress', int(total_seconds * 0.42), 3, {'playback_rate': 1.0}),
                ('scroll', int(total_seconds * 0.16), 6, {}),
                ('exercise_submit', int(total_seconds * 0.28), gap, {'success': self.is_success(student, day_index, profile), 'attempt_count': 1}),
                ('lesson_complete', int(total_seconds * 0.14), gap + 4, {'score': round(profile['success_rate'] * 100, 1)}),
            )
            for event_index, (event_type, duration_seconds, minute_offset, metadata) in enumerate(events):
                event_id = f'{EVENT_PREFIX}:{student.id}:{segment}:{stat_date.isoformat()}:{event_index}'
                LearningEvent.objects.update_or_create(
                    event_id=event_id,
                    defaults={
                        'user': student,
                        'course': path,
                        'lesson': lesson,
                        'knowledge_point': concept,
                        'event_type': event_type,
                        'event_time': day_start + timedelta(minutes=minute_offset),
                        'device_id': f'seed-device-{student.id}',
                        'device_type': 'desktop',
                        'client_session_id': session_id,
                        'page_visible': True,
                        'duration_ms': min(duration_seconds * 1000, 1800000),
                        'progress': min(100, 20 + event_index * 20),
                        'metadata': {'source': 'seeded_profile', **metadata},
                    },
                )

    def seed_legacy_behaviors(self, student, profile, concepts, start_date, end_date, active_days, segment):
        source_prefix = f'{EVENT_PREFIX}:{student.id}:{segment}:'
        UserLearningBehavior.objects.filter(user=student, session_id__startswith=source_prefix).delete()
        behavior_types = ('view_theory', 'view_lab', 'start_lab', 'submit_flag', 'complete_lab', 'complete_module')
        for day_index, stat_date in enumerate(spaced_dates(start_date, end_date, active_days)):
            concept = concepts[day_index % len(concepts)]
            session_id = f'{source_prefix}{stat_date.isoformat()}'
            for event_index, behavior_type in enumerate(behavior_types):
                success = self.is_success(student, day_index + event_index, profile) if behavior_type in {'submit_flag', 'complete_lab'} else None
                behavior = UserLearningBehavior.objects.create(
                    user=student,
                    behavior_type=behavior_type,
                    time_spent=180 + event_index * 70,
                    success=success,
                    score=round(profile['success_rate'] * 100, 1) if success is not None else None,
                    session_id=session_id,
                )
                behavior.concepts.add(concept)
                UserLearningBehavior.objects.filter(pk=behavior.pk).update(
                    timestamp=timezone.make_aware(datetime.combine(stat_date, time(hour=19, minute=event_index * 4))),
                )
    @staticmethod
    def is_success(student, day_index, profile):
        threshold = int(profile['success_rate'] * 100)
        return ((student.id * 13 + day_index * 29) % 100) < threshold

    @staticmethod
    def rebuild_snapshots(student, today):
        for days in (90, 30, 7):
            current_start, current_end = period_bounds(days, today)
            previous_start, previous_end = period_bounds(days, current_start.date() - timedelta(days=1))
            rebuild_user_analytics(student, previous_start, previous_end)
            rebuild_user_analytics(student, current_start, current_end)


def path_for_event(lesson):
    return lesson.learning_path if lesson is not None else LearningPath.objects.order_by('id').first()






