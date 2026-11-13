from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from resources.models import Resource


class ResourceQueryAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_user(username='audit-resource-admin', role='admin')
        cls.student = users.objects.create_user(username='audit-resource-student', role='student')
        cls.resource = Resource.objects.create(
            title='Audit review resource', description='Synthetic fixture',
            resource_type='document', category='Audit', file='resources/audit.txt',
            uploader=cls.admin, status='pending',
        )

    def test_invalid_resource_ordering_is_a_client_error(self):
        for path, user in (('/api/resources/', None), ('/api/resources/admin/', self.admin)):
            client = APIClient()
            if user:
                client.force_authenticate(user)
            for value in ('unknown', 'uploader__password', '--created_at'):
                with self.subTest(path=path, ordering=value):
                    response = client.get(path, {'ordering': value})
                    self.assertEqual(response.status_code, 400, response.data)

    def test_role_administrator_can_review_and_records_review_time(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post('/api/resources/review/', {'resource_id': self.resource.pk, 'status': 'approved'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.reviewer_id, self.admin.pk)
        self.assertIsNotNone(self.resource.reviewed_at)
        self.assertEqual(client.get('/api/resources/admin/').status_code, 200)

    def test_student_cannot_review_resource(self):
        client = APIClient()
        client.force_authenticate(self.student)
        response = client.post('/api/resources/review/', {'resource_id': self.resource.pk, 'status': 'approved'}, format='json')
        self.assertEqual(response.status_code, 403)
