"""Business flows must keep working with real runtime field encryption enabled."""
import secrets

from django.test import TestCase
from rest_framework.test import APIClient

from data_security.adapters.persistence import fields
from data_security.runtime.crypto import RuntimeCipher
from data_security.runtime.fields import RuntimeFieldStorage
from users.models import CTFUser


class RuntimeBusinessTests(TestCase):
    def setUp(self):
        self.addCleanup(fields.bind_field_storage, fields._adapter)
        fields.bind_field_storage(RuntimeFieldStorage(RuntimeCipher(secrets.token_bytes(64))))
        self.password = secrets.token_urlsafe(24)
        self.user = CTFUser.objects.create_user(username='runtime-business',
            password=self.password, email='business@example.invalid')
        self.other = CTFUser.objects.create_user(username='runtime-other-business')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_cookie_login_and_profile_update_preserve_encrypted_email(self):
        client = APIClient(enforce_csrf_checks=True)
        client.get('/api/users/csrf/')
        response = client.post('/api/users/login/', {'username': self.user.username,
            'password': self.password}, format='json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 200)
        response = client.put('/api/users/profile/update/', {'nickname': 'Updated'},
            format='json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '')
        self.assertEqual(self.user.read_protected('email'), 'business@example.invalid')
        self.assertEqual(response.data['user']['protection']['email']['storage'], 'encrypted')

    def test_conversation_decrypts_and_redacts_for_owner_and_denies_other_accounts(self):
        from ai_assistant.models import AIConversation, AIMessage
        conversation = AIConversation.objects.create(user=self.user)
        message = AIMessage.objects.create(conversation=conversation, role='user',
            content='请解释参数化查询 business@example.invalid', metadata={'email': 'business@example.invalid'})
        response = self.client.get(f'/api/ai/conversations/{conversation.pk}/')
        self.assertEqual(response.status_code, 200)
        row = response.data['messages'][0]
        self.assertIn('请解释参数化查询', row['content'])
        self.assertNotIn('business@example.invalid', str(row))
        self.assertEqual(row['protection']['content']['storage'], 'encrypted')
        message.refresh_from_db()
        self.assertEqual(message.content, '')
        self.assertEqual(message.metadata, {})
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/ai/conversations/{conversation.pk}/').status_code, 404)

    def test_interview_repeated_answers_preserve_prior_encrypted_values(self):
        from student_profiles.models import OnboardingInterview
        url = '/api/student-profiles/onboarding/interview/'
        for number, answer in ((1, '我想学习网络安全'), (2, '我已掌握 Python 基础')):
            response = self.client.post(url, {'question_id': number, 'answer': answer}, format='json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['protection']['answers']['storage'], 'encrypted')
        interview = OnboardingInterview.objects.get(profile__user=self.user)
        self.assertEqual(interview.answers, {})
        self.assertEqual(interview.read_protected('answers'), {'1': '我想学习网络安全', '2': '我已掌握 Python 基础'})

    def test_signed_history_survives_encryption_and_source_access_revocation(self):
        from ai_assistant.history import Origin, REDACTED, create_message, history_message
        from ai_assistant.models import AIConversation
        from articles.models import Article
        article = Article.objects.create(author=self.other, title='公开教材', content='参数化查询', status='approved')
        origin = Origin(self.user)
        origin.add('article', article.pk)
        conversation = AIConversation.objects.create(user=self.user)
        message = create_message(origin=origin, conversation=conversation, role='assistant',
            content='参数化查询讲解', metadata={'note': 'internal'})
        message.refresh_from_db()
        self.assertEqual(message.content, '')
        self.assertEqual(history_message(message, self.user)['content'], '参数化查询讲解')
        self.assertEqual(history_message(message, self.other)['content'], REDACTED)
        article.status = 'rejected'
        article.save(update_fields=['status'])
        self.assertEqual(history_message(message, self.user)['content'], REDACTED)
