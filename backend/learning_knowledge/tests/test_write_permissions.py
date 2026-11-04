"""HTTP regression inventory for existing module-three write authority."""

from django.test import TestCase
from rest_framework.test import APIClient

from learning_knowledge.models import CourseGrant, Material, MaterialChunk, MaterialRevision, ReviewAction
from learning_knowledge.review import parse_candidate, register
from users.models import CTFUser
from .helpers import setup_case
from .test_review import metadata


class TeachingWritePermissionTests(TestCase):
    def setUp(self):
        setup_case(self)
        self.client = APIClient()
        self.revision = register(
            actor=self.teacher, catalog=self.task.catalog, material_class='lesson',
            tasks=[self.task], metadata=metadata(),
        )
        parse_candidate(revision_id=self.revision.pk, token=self.revision.ingestion_token)
        self.root = '/api/teaching-knowledge/'
        self.material_url = f'{self.root}materials/{self.revision.material.material_id}/'

    def registration(self, **overrides):
        return {
            'catalog_version': self.task.catalog.version, 'material_class': 'lesson',
            'task_ids': [self.task.pk], 'metadata': metadata(), **overrides,
        }

    def action_data(self, action, revision=1):
        return {'expected_revision': revision, 'idempotency_key': f'{action}-{revision}', 'reason': 'Synthetic review.'}

    def test_student_material_create_denied_even_with_review_grant(self):
        CourseGrant.objects.filter(user=self.student).update(can_review=True)
        self.client.force_authenticate(self.student)
        for material_class in ('lesson', 'hint', 'student_analysis', 'teacher_answer', 'grading_secret'):
            with self.subTest(material_class=material_class):
                data = self.registration(material_class=material_class)
                if material_class == 'hint':
                    data['hint_level'] = 1
                response = self.client.post(f'{self.root}materials/', data, format='json')
                self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(Material.objects.count(), 1)
        self.assertEqual(MaterialRevision.objects.count(), 1)

    def test_student_revision_write_retains_not_found_boundary(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(self.material_url + 'revisions/', {
            'task_ids': [self.task.pk], 'metadata': metadata('Replacement draft.'),
        }, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(MaterialRevision.objects.count(), 1)
        self.assertEqual(MaterialChunk.objects.count(), 1)

    def test_student_submit_approve_publish_withdraw_denied(self):
        self.client.force_authenticate(self.student)
        for action in ('submit', 'approve', 'publish', 'withdraw'):
            with self.subTest(action=action):
                response = self.client.post(self.material_url + action + '/', self.action_data(action), format='json')
                self.assertEqual(response.status_code, 404, response.data)
        self.assertFalse(ReviewAction.objects.exists())
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.review_status, 'draft')

    def test_student_and_teacher_grant_writes_denied_admin_allowed(self):
        payload = {'catalog_version': self.task.catalog.version, 'user_id': self.other.pk, 'active': True}
        for actor in (self.student, self.teacher):
            with self.subTest(role=actor.role):
                self.client.force_authenticate(actor)
                self.assertEqual(self.client.post(self.root + 'grants/', payload, format='json').status_code, 403)
        self.assertFalse(CourseGrant.objects.filter(user=self.other).exists())
        self.client.force_authenticate(self.admin)
        response = self.client.post(self.root + 'grants/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(CourseGrant.objects.filter(user=self.other, active=True).exists())

    def test_teacher_material_create_and_revision_success(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post(self.root + 'materials/', self.registration(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        url = f'{self.root}materials/{response.data["material_id"]}/revisions/'
        response = self.client.post(url, {
            'task_ids': [self.task.pk], 'metadata': metadata('New teacher draft.'),
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['revision'], 2)
        self.assertEqual(MaterialRevision.objects.filter(parse_status='completed').count(), 3)

    def test_independent_teacher_review_publish_and_withdraw_success(self):
        reviewer = CTFUser.objects.create_user(username='m3-second-reviewer', role='teacher')
        CourseGrant.objects.create(user=reviewer, catalog=self.task.catalog, can_review=True)
        for action, actor, expected in (
            ('submit', self.teacher, 'in_review'), ('approve', reviewer, 'approved'),
            ('publish', self.teacher, 'published'), ('withdraw', self.teacher, 'withdrawn'),
        ):
            with self.subTest(action=action):
                self.client.force_authenticate(actor)
                response = self.client.post(self.material_url + action + '/', self.action_data(action), format='json')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['review_status'], expected)
        self.assertEqual(ReviewAction.objects.count(), 4)

    def test_teacher_without_review_grant_cannot_create_or_revise(self):
        CourseGrant.objects.filter(user=self.teacher).update(can_review=False)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.post(self.root + 'materials/', self.registration(), format='json').status_code, 403)
        self.assertEqual(self.client.post(self.material_url + 'revisions/', {
            'task_ids': [self.task.pk], 'metadata': metadata(),
        }, format='json').status_code, 404)
        self.assertEqual(MaterialRevision.objects.count(), 1)

    def test_staff_bit_does_not_replace_module_three_admin_or_teacher_role(self):
        self.student.is_staff = True
        self.student.save(update_fields=['is_staff'])
        CourseGrant.objects.filter(user=self.student).update(can_review=True, maintain_secrets=True)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.post(self.root + 'materials/', self.registration(), format='json').status_code, 403)
        self.assertEqual(self.client.post(self.root + 'grants/', {
            'catalog_version': self.task.catalog.version, 'user_id': self.other.pk,
        }, format='json').status_code, 403)
        self.assertEqual(Material.objects.count(), 1)

    def test_grading_secret_still_requires_admin_and_maintenance_grant(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.post(self.root + 'materials/', self.registration(material_class='grading_secret'), format='json').status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(self.root + 'materials/', self.registration(material_class='grading_secret'), format='json').status_code, 403)
        CourseGrant.objects.create(user=self.admin, catalog=self.task.catalog, maintain_secrets=True)
        response = self.client.post(self.root + 'materials/', self.registration(material_class='grading_secret'), format='json')
        self.assertEqual(response.status_code, 201, response.data)
