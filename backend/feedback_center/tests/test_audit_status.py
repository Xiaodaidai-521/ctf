from django.test import TestCase, override_settings
from rest_framework.test import APIClient


class FeedbackStatusRegressionTests(TestCase):
    def test_status_agrees_with_actual_phase3_gates(self):
        client = APIClient()
        for enabled, release in ((False, False), (True, False), (True, True)):
            with self.subTest(enabled=enabled, release=release), override_settings(FEEDBACK_PHASE3_ENABLED=enabled, FEEDBACK_PHASE3_RELEASE_ENABLED=release):
                response = client.get('/api/feedback/status/')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data['candidate_management_enabled'], enabled)
                self.assertEqual(response.data['candidate_release_enabled'], release)
