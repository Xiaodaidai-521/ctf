from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from users.models import CTFUser
from challenges.models import Category, Challenge
from .models import LearningPath, PathModule, UserPathProgress, UserModuleProgress, UserLabProgress, LabAttempt, UserLearningBehavior, KnowledgeConcept, ConceptResource


class PathManagementRegressionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.teacher = CTFUser.objects.create_user(username='audit-path-teacher', role='teacher')
        self.student = CTFUser.objects.create_user(username='audit-path-student')
        self.draft = LearningPath.objects.create(title='Draft path', slug='audit-draft', difficulty='AP')
        self.published = LearningPath.objects.create(title='Published path', slug='audit-published', difficulty='AP', is_published=True)
        self.module = PathModule.objects.create(learning_path=self.draft, title='Draft module', module_type='theory', content='draft material')

    def test_teacher_can_manage_draft_but_students_cannot_read_it(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(f'/api/learning-paths/paths/{self.draft.pk}/').status_code, 200)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(f'/api/learning-paths/paths/{self.draft.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/learning-paths/modules/{self.module.pk}/').status_code, 404)

    def test_teacher_creates_and_updates_path_and_module_with_model_fields(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post('/api/learning-paths/paths/', {'title': 'New draft', 'description': 'Goal', 'difficulty': 'AP', 'is_published': False}, format='json')
        self.assertEqual(response.status_code, 201)
        path_id = response.data['id']
        self.assertTrue(response.data['slug'])
        module = self.client.post('/api/learning-paths/modules/', {'learning_path': path_id, 'title': 'New module', 'module_type': 'theory', 'content': 'actual content', 'estimated_minutes': 20}, format='json')
        self.assertEqual(module.status_code, 201)
        changed = self.client.patch(f'/api/learning-paths/modules/{module.data["id"]}/', {'content': 'updated content'}, format='json')
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.data['content'], 'updated content')
        published = self.client.patch(f'/api/learning-paths/paths/{path_id}/', {'is_published': True}, format='json')
        self.assertEqual(published.status_code, 200)
        self.assertTrue(published.data['is_published'])
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(f'/api/learning-paths/paths/{path_id}/').status_code, 200)

    def test_anonymous_progress_requires_authentication(self):
        self.assertEqual(self.client.get(f'/api/learning-paths/paths/{self.published.pk}/progress/').status_code, 403)

    def test_student_cannot_create_paths_or_modules(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.post('/api/learning-paths/paths/', {}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/learning-paths/modules/', {}, format='json').status_code, 403)

    def test_progress_counts_only_required_modules(self):
        required = PathModule.objects.create(learning_path=self.published, title='Required', module_type='theory', is_required=True)
        optional = PathModule.objects.create(learning_path=self.published, title='Optional', module_type='theory', is_required=False)
        progress = UserPathProgress.objects.create(user=self.student, learning_path=self.published)
        UserModuleProgress.objects.create(user=self.student, module=optional, status='COMPLETED')
        progress.update_progress()
        self.assertEqual(progress.progress_percentage, 0)
        UserModuleProgress.objects.create(user=self.student, module=required, status='COMPLETED')
        progress.update_progress()
        self.assertEqual(progress.progress_percentage, 100)

    def test_locked_module_cannot_skip_start_and_completed_retry_is_idempotent(self):
        self.client.force_authenticate(self.student)
        module = PathModule.objects.create(learning_path=self.published, title='Required', module_type='theory')
        progress = UserModuleProgress.objects.create(user=self.student, module=module, status='LOCKED')
        endpoint = f'/api/learning-paths/modules/{module.pk}/complete/'
        self.assertEqual(self.client.post(endpoint, {}, format='json').status_code, 400)
        self.assertEqual(self.client.post(f'/api/learning-paths/modules/{module.pk}/start/', {}, format='json').status_code, 200)
        for _ in range(2):
            self.assertEqual(self.client.post(endpoint, {}, format='json').status_code, 200)
        self.assertEqual(UserLearningBehavior.objects.filter(user=self.student, behavior_type='complete_module').count(), 1)

    def test_legacy_lab_attempt_uses_server_flag_check_and_model_contract(self):
        category = Category.objects.create(name='audit-legacy-lab')
        challenge = Challenge.objects.create(title='Legacy lab', category=category, difficulty='easy', score=10, flag='flag{audit-lab}')
        progress = UserLabProgress.objects.create(user=self.student, lab=challenge, status='IN_PROGRESS')
        self.client.force_authenticate(self.student)
        response = self.client.post('/api/learning-paths/lab-attempts/', {'lab_id': challenge.pk, 'answer': 'wrong', 'success': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['is_correct'])
        denied = self.client.patch(f'/api/learning-paths/lab-attempts/{response.data["id"]}/', {'success': True}, format='json')
        self.assertEqual(denied.status_code, 405)
        correct = self.client.post('/api/learning-paths/lab-attempts/', {'lab_id': challenge.pk, 'answer': 'flag{audit-lab}'}, format='json')
        self.assertEqual(correct.status_code, 200)
        self.assertTrue(correct.data['is_correct'])
        progress.refresh_from_db()
        self.assertEqual(progress.status, 'COMPLETED')
        self.assertIsNotNone(progress.first_completed_at)
        self.assertEqual(self.client.get('/api/learning-paths/lab-attempts/').status_code, 200)
        for attempt in LabAttempt.objects.filter(user=self.student):
            self.assertNotIn('flag{audit-lab}', str(attempt.payload))

    def test_recommendations_require_registered_published_module_links(self):
        self.client.force_authenticate(self.student)
        endpoint = '/api/learning-paths/recommendations/'
        self.assertEqual(self.client.get(endpoint).data['recommendations'], [])
        concept = KnowledgeConcept.objects.create(name='Audit concept', slug='audit-concept', concept_type='tech')
        module_type = ContentType.objects.get_for_model(PathModule)
        ConceptResource.objects.create(concept=concept, content_type=module_type, object_id=self.module.pk)
        self.assertEqual(self.client.get(endpoint).data['recommendations'], [])
        published_module = PathModule.objects.create(learning_path=self.published, title='Published module', module_type='theory')
        ConceptResource.objects.create(concept=concept, content_type=module_type, object_id=published_module.pk)
        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['path_id'] for item in response.data['recommendations']], [self.published.pk])
        self.assertEqual(response.data['provider'], 'deterministic_learning_rules')
