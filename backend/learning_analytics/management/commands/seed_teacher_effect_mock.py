from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from learning_analytics.models import DailyLearningStat, LearningEffectSnapshot, LearningRecommendation
from learning_analytics.services import ALGORITHM_VERSION
from users.models import CTFUser


SEED_SOURCE = 'teacher_effect_mock_stu_selected'
DIMENSION_KEYS = (
    'time_score',
    'completion_score',
    'mastery_score',
    'retention_score',
    'consistency_score',
    'efficiency_score',
    'engagement_score',
    'focus_score',
)


def clamp(value, low=0, high=100):
    return max(low, min(high, value))


def effect_level(score):
    if score >= 85:
        return 'excellent'
    if score >= 70:
        return 'good'
    if score >= 50:
        return 'developing'
    return 'at_risk'


class Command(BaseCommand):
    help = 'Seed short teacher learning-effect mock history. Use --users to avoid creating accounts.'

    def add_arguments(self, parser):
        parser.add_argument('--start', type=int, default=12)
        parser.add_argument('--end', type=int, default=126)
        parser.add_argument('--days', type=int, default=90, choices=(7, 30, 90))
        parser.add_argument('--users', nargs='+', help='Seed only these existing usernames. Missing users are skipped.')

    @transaction.atomic
    def handle(self, *args, **options):
        start = options['start']
        end = options['end']
        days = options['days']
        today = timezone.localdate()
        current_start = today - timedelta(days=days - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=days - 1)

        users_created = 0
        current_snapshots = 0
        previous_snapshots = 0
        daily_rows = 0
        recommendations = 0
        skipped = []

        if options.get('users'):
            requested = list(dict.fromkeys(options['users']))
            found = {
                user.username: user
                for user in CTFUser.objects.filter(username__in=requested, role='student')
            }
            targets = []
            for index, username in enumerate(requested, start=1):
                user = found.get(username)
                if not user:
                    skipped.append(username)
                    continue
                targets.append((self.seed_number(username, index), user))
        else:
            targets = []
            for number in range(start, end + 1):
                username = f'stu_{number}'
                user, created = CTFUser.objects.get_or_create(
                    username=username,
                    defaults={
                        'role': 'student',
                        'nickname': f'Student {number}',
                        'student_id': f'2026{number:04d}',
                        'class_name': 'AI Learning Demo',
                        'enrollment_year': 2026,
                    },
                )
                if created:
                    user.set_unusable_password()
                    user.save(update_fields=['password'])
                    users_created += 1
                elif user.role != 'student':
                    user.role = 'student'
                    user.save(update_fields=['role'])
                targets.append((number, user))

        for number, user in targets:
            previous_scores = self.build_scores(number, previous=True)
            current_scores = self.build_scores(number, previous=False)
            previous_snapshots += self.upsert_snapshot(user, previous_start, previous_end, previous_scores, number, 'previous')
            current_snapshots += self.upsert_snapshot(user, current_start, today, current_scores, number, 'current')
            daily_rows += self.upsert_daily_stats(user, current_start, today, current_scores, number)
            recommendations += self.upsert_recommendation(user, current_scores, number)

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {len(targets)} students: '
            f'users_created={users_created}, '
            f'current_snapshots={current_snapshots}, '
            f'previous_snapshots={previous_snapshots}, '
            f'daily_stats={daily_rows}, '
            f'recommendations={recommendations}, '
            f'skipped={skipped}.'
        ))

    @staticmethod
    def seed_number(username, fallback):
        digits = ''.join(ch for ch in username if ch.isdigit())
        if digits:
            return int(digits)
        return 100 + (sum(ord(ch) for ch in username) + fallback) % 37

    def build_scores(self, number, previous=False):
        base = 48 + (number * 7) % 35
        if previous:
            base -= 4 + number % 5
        else:
            base += number % 8
        scores = {}
        for index, key in enumerate(DIMENSION_KEYS):
            wobble = ((number + index * 11) % 17) - 8
            if key in {'consistency_score', 'focus_score'}:
                wobble -= 3
            scores[key] = round(clamp(base + wobble), 2)
        total = round(sum(scores.values()) / len(scores), 2)
        return scores, total

    def upsert_snapshot(self, user, start_date, end_date, score_pack, number, segment):
        scores, total = score_pack
        effective_seconds = int((18 + (number % 11) * 2 + (0 if segment == 'previous' else 5)) * 3600)
        question_count = 12 + number % 18
        correct_rate = clamp(scores['mastery_score'] + (number % 5) - 2)
        defaults = {
            **scores,
            'total_effect_score': total,
            'effect_level': effect_level(total),
            'confidence_score': round(0.72 + (number % 9) * 0.02, 2),
            'sample_description': {
                'source': SEED_SOURCE,
                'segment': segment,
                'effective_learning_seconds': effective_seconds,
                'session_count': 4 + number % 5,
                'completed_lesson_count': 1 + number % 4,
                'question_count': question_count,
                'correct_question_count': round(question_count * correct_rate / 100),
            },
        }
        LearningEffectSnapshot.objects.update_or_create(
            user=user,
            analysis_start_date=start_date,
            analysis_end_date=end_date,
            algorithm_version=ALGORITHM_VERSION,
            defaults=defaults,
        )
        return 1

    def upsert_daily_stats(self, user, start_date, end_date, score_pack, number):
        scores, total = score_pack
        rows = 0
        sample_offsets = (0, 12, 24, 36, 48, 60, 72, 89)
        for offset in sample_offsets:
            stat_date = min(start_date + timedelta(days=offset), end_date)
            seconds = int((35 + (number + offset) % 50) * 60)
            questions = 2 + (number + offset) % 6
            correct = round(questions * clamp(scores['mastery_score'] + offset % 7 - 3) / 100)
            DailyLearningStat.objects.update_or_create(
                user=user,
                stat_date=stat_date,
                algorithm_version=ALGORITHM_VERSION,
                defaults={
                    'raw_learning_seconds': seconds + 480,
                    'active_learning_seconds': seconds + 180,
                    'effective_learning_seconds': seconds,
                    'video_learning_seconds': seconds // 4,
                    'reading_learning_seconds': seconds // 3,
                    'practice_learning_seconds': seconds // 3,
                    'review_learning_seconds': seconds // 12,
                    'session_count': 1 + offset % 3,
                    'completed_lesson_count': 1 if offset % 24 == 0 else 0,
                    'question_count': questions,
                    'correct_question_count': correct,
                    'correct_rate': round(correct / questions * 100, 2) if questions else 0,
                    'knowledge_point_count': 1 + (number + offset) % 4,
                    'focus_score': scores['focus_score'],
                    'fragmentation_rate': round(0.12 + ((number + offset) % 8) * 0.03, 2),
                    'effect_score': total,
                },
            )
            rows += 1
        return rows

    def upsert_recommendation(self, user, score_pack, number):
        scores, total = score_pack
        weakest_key = min(scores, key=scores.get)
        title_map = {
            'time_score': '补足学习时长',
            'completion_score': '推进课程完成',
            'mastery_score': '巩固知识掌握',
            'retention_score': '安排复习回看',
            'consistency_score': '保持学习连续',
            'efficiency_score': '优化练习效率',
            'engagement_score': '提高参与度',
            'focus_score': '减少分心中断',
        }
        LearningRecommendation.objects.filter(
            user=user,
            recommendation_type='mock_learning_effect',
            algorithm_version=ALGORITHM_VERSION,
            evidence__source=SEED_SOURCE,
        ).delete()
        LearningRecommendation.objects.create(
            user=user,
            recommendation_type='mock_learning_effect',
            priority=1 if total < 55 else 2,
            severity='warning' if total < 55 else 'info',
            title=title_map.get(weakest_key, '学习效果优化'),
            content='本周保持 2 次短练习，并复盘最近错题。',
            reason=f'{weakest_key} 当前为 {scores[weakest_key]:.0f} 分，建议优先补强。',
            evidence={'source': SEED_SOURCE, 'student_no': number, 'weakest_key': weakest_key},
            action_text='查看学习路径',
            expected_benefit='提升下一周期综合学习效果',
            status='active',
            algorithm_version=ALGORITHM_VERSION,
        )
        return 1