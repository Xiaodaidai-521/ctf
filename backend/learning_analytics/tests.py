from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from resources.models import Resource
from users.models import CTFUser

from .models import AdminLearningScore, LearningAdjustmentProposal, LearningBehaviorEvent
from .tasks import cleanup_expired_behavior_events
from .views import build_effect_score


class TeacherHandoffAnalyticsTests(TestCase):
    def setUp(self):
        self.teacher = CTFUser.objects.create_user(username='teacher', password='Password123!', role='teacher')
        self.admin = CTFUser.objects.create_user(username='admin', password='Password123!', role='admin')
        self.student = CTFUser.objects.create_user(username='student', password='Password123!', role='student')
        self.client = APIClient()

    def create_five_signal_events(self):
        LearningBehaviorEvent.objects.create(student=self.student, event_type='resource_retrieved')
        LearningBehaviorEvent.objects.create(student=self.student, event_type='resource_downloaded')
        LearningBehaviorEvent.objects.create(student=self.student, event_type='module_completed')
        LearningBehaviorEvent.objects.create(student=self.student, event_type='challenge_submitted', metadata={'success': True})
        LearningBehaviorEvent.objects.create(student=self.student, event_type='exam_submitted', metadata={'normalized_score': 80})

    def test_effect_score_uses_all_five_signals(self):
        self.create_five_signal_events()

        effect = build_effect_score(self.student)

        self.assertEqual(set(effect['signals']), {
            'resource_retrieval', 'resource_download', 'module_completion',
            'challenge_success', 'exam_performance',
        })
        self.assertEqual(effect['signals']['challenge_success']['score'], 100)
        self.assertEqual(effect['signals']['exam_performance']['score'], 80)
        self.assertGreater(effect['effect_score'], 0)

    def test_teacher_can_read_behavior_and_create_proposal(self):
        self.create_five_signal_events()
        self.client.force_authenticate(self.teacher)

        behavior = self.client.get(f'/api/analytics/teacher/students/{self.student.id}/behavior/')
        self.assertEqual(behavior.status_code, 200)
        self.assertEqual(behavior.data['student']['id'], self.student.id)
        self.assertEqual(behavior.data['effect']['signals']['exam_performance']['event_count'], 1)

        response = self.client.post('/api/analytics/teacher/proposals/', {
            'student': self.student.id,
            'title': 'Practice retrieval and review',
            'rationale': 'Recent learning activity needs reinforcement.',
            'adjustments': {'resource_priority': 'web'},
            'status': 'active',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        proposal = LearningAdjustmentProposal.objects.get(id=response.data['id'])

        effect = self.client.get(f'/api/analytics/teacher/proposals/{proposal.id}/effect/')
        self.assertEqual(effect.status_code, 200)
        self.assertIn('effect_score', effect.data)

    def test_admin_is_forbidden_from_teacher_endpoints(self):
        proposal = LearningAdjustmentProposal.objects.create(
            teacher=self.teacher,
            student=self.student,
            title='Teacher proposal',
        )
        self.client.force_authenticate(self.admin)

        self.assertEqual(
            self.client.get(f'/api/analytics/teacher/students/{self.student.id}/behavior/').status_code,
            403,
        )
        self.assertEqual(self.client.get('/api/analytics/teacher/proposals/').status_code, 403)
        self.assertEqual(
            self.client.get(f'/api/analytics/teacher/proposals/{proposal.id}/effect/').status_code,
            403,
        )

    def test_cleanup_deletes_events_older_than_ninety_days(self):
        expired = LearningBehaviorEvent.objects.create(student=self.student, event_type='module_completed')
        LearningBehaviorEvent.objects.filter(id=expired.id).update(
            occurred_at=timezone.now() - timedelta(days=91),
        )
        current = LearningBehaviorEvent.objects.create(student=self.student, event_type='module_completed')

        self.assertEqual(cleanup_expired_behavior_events(), 1)
        self.assertFalse(LearningBehaviorEvent.objects.filter(id=expired.id).exists())
        self.assertTrue(LearningBehaviorEvent.objects.filter(id=current.id).exists())


class TeacherAnalyticsCompatibilityTests(TestCase):
    def setUp(self):
        self.teacher = CTFUser.objects.create_user(username='teacher', password='Password123!', role='teacher')
        self.admin = CTFUser.objects.create_user(username='admin', password='Password123!', role='admin')
        self.student = CTFUser.objects.create_user(username='student', password='Password123!', role='student')
        self.client = APIClient()

    def test_teacher_analytics_compatibility_routes_reuse_existing_data(self):
        LearningBehaviorEvent.objects.create(student=self.student, event_type='module_completed')
        proposal = LearningAdjustmentProposal.objects.create(
            teacher=self.teacher,
            student=self.student,
            title='Initial adjustment',
        )
        self.client.force_authenticate(self.teacher)

        effect = self.client.get(f'/api/analytics/teacher/learning-effect/?student_id={self.student.id}')
        self.assertEqual(effect.status_code, 200)
        self.assertEqual(effect.data['student']['id'], self.student.id)
        self.assertIn('effect_score', effect.data['effect'])
        self.assertEqual(
            self.client.post('/api/analytics/teacher/learning-effect/', {'student_id': self.student.id}, format='json').status_code,
            200,
        )

        adjustment = self.client.post(
            f'/api/analytics/teacher/adjustments/{proposal.id}/',
            {'status': 'active', 'adjustments': {'focus': 'web'}},
            format='json',
        )
        self.assertEqual(adjustment.status_code, 200)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, 'active')
        self.assertEqual(proposal.adjustments, {'focus': 'web'})

        score = self.client.post('/api/analytics/teacher/scores/', {
            'student': self.student.id,
            'measured_at': timezone.localdate().isoformat(),
            'total_score': 80,
            'dimension_scores': {'web': 80},
            'tags': ['baseline'],
        }, format='json')
        self.assertEqual(score.status_code, 201)
        self.assertTrue(AdminLearningScore.objects.filter(id=score.data['id'], scored_by=self.teacher).exists())
        self.assertEqual(
            self.client.get(f'/api/analytics/teacher/scores/?student_id={self.student.id}').status_code,
            200,
        )

        plan = self.client.get(f'/api/analytics/teacher/teaching-plan/{self.student.id}/')
        self.assertEqual(plan.status_code, 200)
        self.assertEqual(plan.data['student'], self.student.id)
        report = self.client.get('/api/analytics/teacher/student-report/')
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data[0]['id'], self.student.id)

    def test_resource_feedback_detail_route_uses_resource_id_from_path(self):
        resource = Resource.objects.create(
            title='Guide',
            description='Guide description',
            resource_type='document',
            file=SimpleUploadedFile('guide.txt', b'guide'),
            category='web',
            uploader=self.teacher,
            status='approved',
        )
        self.client.force_authenticate(self.student)

        response = self.client.post(
            f'/api/analytics/resource-feedback/{resource.id}/',
            {'rating': 5, 'helpful': True, 'comment': 'Useful'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['resource'], resource.id)
        self.assertEqual(
            self.client.get(f'/api/analytics/resource-feedback/{resource.id}/').data['rating'],
            5,
        )

    def test_admin_is_forbidden_from_teacher_compatibility_routes(self):
        proposal = LearningAdjustmentProposal.objects.create(
            teacher=self.teacher,
            student=self.student,
            title='Adjustment',
        )
        self.client.force_authenticate(self.admin)

        requests = [
            self.client.get(f'/api/analytics/teacher/learning-effect/?student_id={self.student.id}'),
            self.client.post(f'/api/analytics/teacher/adjustments/{proposal.id}/', {'status': 'active'}, format='json'),
            self.client.get('/api/analytics/teacher/scores/'),
            self.client.post('/api/analytics/teacher/scores/', {}, format='json'),
            self.client.get(f'/api/analytics/teacher/teaching-plan/{self.student.id}/'),
            self.client.get('/api/analytics/teacher/student-report/'),
        ]
        self.assertTrue(all(response.status_code == 403 for response in requests))
