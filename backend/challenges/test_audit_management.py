from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from challenges.models import Category, Challenge


class ChallengeManagementAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.teacher = users.objects.create_user(username='audit-challenge-teacher', role='teacher')
        cls.admin = users.objects.create_user(username='audit-challenge-admin', role='admin')
        cls.student = users.objects.create_user(username='audit-challenge-student', role='student')
        cls.category = Category.objects.create(name='Audit challenge category')
        cls.challenge = Challenge.objects.create(
            title='Inactive managed challenge', description='Audit fixture',
            category=cls.category, difficulty='easy', score=10,
            flag='flag{original-audit-answer}', is_active=False,
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def payload(self, **changes):
        payload = {
            'title': 'Audit created challenge', 'description': 'Audit fixture',
            'category': self.category.pk, 'difficulty': 'easy', 'score': 10,
            'flag': 'flag{created-audit-answer}',
        }
        payload.update(changes)
        return payload

    def test_management_create_saves_flag_without_returning_it(self):
        response = self.client_for(self.teacher).post('/api/challenges/challenges/', self.payload(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn('flag', response.data)
        challenge = Challenge.objects.get(pk=response.data['id'])
        self.assertEqual(challenge.read_protected('flag'), 'flag{created-audit-answer}')
        submitted = self.client_for(self.student).post(
            f'/api/challenges/challenges/{challenge.pk}/submit/',
            {'flag': 'flag{created-audit-answer}'}, format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.assertTrue(submitted.data['success'])

    def test_scored_challenge_requires_flag_on_create(self):
        for flag in (None, ''):
            with self.subTest(flag=flag):
                data = self.payload()
                if flag is None:
                    data.pop('flag')
                else:
                    data['flag'] = flag
                response = self.client_for(self.teacher).post('/api/challenges/challenges/', data, format='json')
                self.assertEqual(response.status_code, 400, response.data)

    def test_management_can_edit_inactive_challenge_and_replace_flag(self):
        for user in (self.teacher, self.admin):
            with self.subTest(role=user.role):
                client = self.client_for(user)
                url = f'/api/challenges/challenges/{self.challenge.pk}/'
                self.assertEqual(client.get(url).status_code, 200)
                response = client.patch(url, {'flag': f'flag{{replacement-{user.role}}}'}, format='json')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertNotIn('flag', response.data)
                self.challenge.refresh_from_db()
                self.assertEqual(self.challenge.read_protected('flag'), f'flag{{replacement-{user.role}}}')

    def test_omitted_flag_preserves_answer_and_students_cannot_manage(self):
        self.challenge.is_active = True
        self.challenge.save(update_fields=['is_active'])
        url = f'/api/challenges/challenges/{self.challenge.pk}/'
        response = self.client_for(self.teacher).patch(url, {'title': 'Updated audit title'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.read_protected('flag'), 'flag{original-audit-answer}')
        self.assertNotIn('flag', self.client_for(self.student).get(url).data)
        denied = self.client_for(self.student).patch(url, {'flag': 'flag{forged}'}, format='json')
        self.assertEqual(denied.status_code, 403)

    def test_inactive_challenges_are_hidden_from_students(self):
        response = self.client_for(self.student).get(f'/api/challenges/challenges/{self.challenge.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_invalid_category_is_a_client_error(self):
        for category in ('invalid', '0', '-1'):
            with self.subTest(category=category):
                response = APIClient().get('/api/challenges/challenges/', {'category': category})
                self.assertEqual(response.status_code, 400, response.data)

    def test_invalid_score_and_container_port_are_rejected(self):
        for changes in ({'score': -1}, {'redirect_port': 0}, {'redirect_port': 65536}):
            with self.subTest(changes=changes):
                response = self.client_for(self.teacher).post('/api/challenges/challenges/', self.payload(**changes), format='json')
                self.assertEqual(response.status_code, 400, response.data)
