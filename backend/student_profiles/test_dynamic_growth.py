from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APITestCase

from learning_analytics.models import LearningBehaviorEvent

from .models import DynamicGrowthProfile, LearningPersona, StudentProfile
from .persona_service import build_persona_input_snapshot


class DynamicGrowthProfileTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='dynamic-growth-user',
            password='StrongPass123!',
            role='student',
        )
        self.client.force_authenticate(self.user)

    def test_growth_endpoint_creates_a_zero_profile_for_a_new_user(self):
        response = self.client.get(reverse('dynamic-growth-profile'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['analysis_status'], 'insufficient_data')
        self.assertEqual(response.data['total_learning_seconds'], 0)
        self.assertEqual(response.data['completed_question_count'], 0)
        self.assertFalse(response.data['eligible_for_ai'])
        self.assertTrue(DynamicGrowthProfile.objects.filter(profile__user=self.user).exists())

    def test_three_persisted_attempts_make_growth_ready_for_analysis(self):
        for index in range(3):
            LearningBehaviorEvent.objects.create(
                student=self.user,
                event_type='challenge_submitted',
                metadata={'success': index != 0},
            )

        response = self.client.get(reverse('dynamic-growth-profile'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['eligible_for_ai'])
        self.assertEqual(response.data['analysis_status'], 'ready')
        self.assertEqual(response.data['completed_question_count'], 3)
        self.assertEqual(response.data['correct_question_count'], 2)
        self.assertEqual(response.data['correct_rate'], 66.67)

    def test_persona_is_not_regenerated_before_the_evidence_gate(self):
        profile = StudentProfile.objects.create(user=self.user)
        LearningPersona.objects.create(profile=profile)

        with patch('student_profiles.views.ensure_learning_persona') as ensure_persona:
            response = self.client.get(reverse('persona'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['dynamic_growth']['eligible_for_ai'])
        ensure_persona.assert_not_called()

    def test_persona_snapshot_contains_the_persisted_growth_summary(self):
        profile = StudentProfile.objects.create(user=self.user)

        snapshot, _ = build_persona_input_snapshot(profile)

        self.assertEqual(snapshot['dynamic_growth_summary']['completed_question_count'], 0)
        self.assertEqual(snapshot['dynamic_growth_summary']['total_learning_seconds'], 0)
        self.assertTrue(DynamicGrowthProfile.objects.filter(profile=profile).exists())

    def test_rebuild_command_uses_the_existing_user_only(self):
        output = StringIO()

        call_command('rebuild_dynamic_growth', '--user-id', str(self.user.id), stdout=output)

        self.assertIn(f'Rebuilt user {self.user.id}', output.getvalue())
