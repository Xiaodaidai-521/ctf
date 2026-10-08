from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from learning_paths.models import KnowledgeConcept, LearningPath, UserLearningBehavior
from users.models import CTFUser

from .models import LearningEffectSnapshot, LearningEvent


class LearningProfileSeedTests(TestCase):
    def setUp(self):
        self.teacher = CTFUser.objects.create_user(username='profile_teacher', password='Password123!', role='teacher')
        self.reference = CTFUser.objects.create_user(username='126', password='Password123!', role='student')
        self.students = [
            CTFUser.objects.create_user(username=f'profile_student_{index}', password='Password123!', role='student')
            for index in range(4)
        ]
        LearningPath.objects.create(
            title='Profile Test Path',
            slug='profile-test-path',
            description='Profile test path',
            difficulty='AP',
            total_modules=3,
        )
        for index in range(3):
            KnowledgeConcept.objects.create(
                name=f'Profile Test Concept {index}',
                slug=f'profile-test-concept-{index}',
                description='Profile test concept',
                concept_type='tech',
            )
        self.client = APIClient()

    def test_seed_is_idempotent_and_preserves_reference_student(self):
        reference_events_before = LearningEvent.objects.filter(user=self.reference).count()
        reference_behaviors_before = UserLearningBehavior.objects.filter(user=self.reference).count()
        call_command('seed_learning_analytics_profiles')
        selected_ids = list(
            LearningEvent.objects.filter(event_id__startswith='learning-profile-20260714:')
            .values_list('user_id', flat=True)
            .distinct()
            .order_by('user_id')
        )
        event_count = LearningEvent.objects.filter(event_id__startswith='learning-profile-20260714:').count()
        call_command('seed_learning_analytics_profiles')

        self.assertEqual(len(selected_ids), 3)
        self.assertEqual(
            LearningEvent.objects.filter(event_id__startswith='learning-profile-20260714:').count(),
            event_count,
        )
        self.assertEqual(LearningEvent.objects.filter(user=self.reference).count(), reference_events_before)
        self.assertEqual(UserLearningBehavior.objects.filter(user=self.reference).count(), reference_behaviors_before)
        self.assertTrue(UserLearningBehavior.objects.filter(user_id__in=selected_ids).exists())

    def test_three_profiles_have_complete_distinct_teacher_summaries(self):
        call_command('seed_learning_analytics_profiles')
        start_date = timezone.localdate() - timedelta(days=89)
        snapshots = list(
            LearningEffectSnapshot.objects.filter(analysis_start_date=start_date)
            .order_by('total_effect_score')
        )
        self.assertEqual(len(snapshots), 3)
        self.assertLess(snapshots[0].total_effect_score, snapshots[1].total_effect_score)
        self.assertLess(snapshots[1].total_effect_score, snapshots[2].total_effect_score)
        self.assertEqual(snapshots[0].effect_level, 'at_risk')
        self.assertEqual(snapshots[2].effect_level, 'excellent')

        self.client.force_authenticate(self.teacher)
        for snapshot in snapshots:
            response = self.client.get(f'/api/analytics/learning/effect/?student_id={snapshot.user_id}&days=90')
            self.assertEqual(response.status_code, 200)
            self.assertIsNotNone(response.data['snapshot'])
            self.assertIsNotNone(response.data['previous_snapshot'])
            self.assertEqual(len(response.data['snapshot']['dimensions']), 8)
            self.assertTrue(response.data['recommendations'])


