import os
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import CTFUser


class BootstrapTeacherCommandTests(TestCase):
    environment = {
        'TEACHER_USERNAME': 'teacher-account',
        'TEACHER_PASSWORD': 'TeacherPassword123!',
        'TEACHER_EMAIL': 'teacher@example.com',
        'TEACHER_RESET_PASSWORD': 'false',
    }

    def run_command(self, **environment):
        values = {**self.environment, **environment}
        with patch.dict(os.environ, values, clear=False):
            call_command('bootstrap_teacher', stdout=StringIO())

    def test_creates_non_privileged_teacher_account(self):
        self.run_command()

        teacher = CTFUser.objects.get(username=self.environment['TEACHER_USERNAME'])
        self.assertEqual(teacher.email, self.environment['TEACHER_EMAIL'])
        self.assertEqual(teacher.role, 'teacher')
        self.assertFalse(teacher.is_staff)
        self.assertFalse(teacher.is_superuser)
        self.assertTrue(teacher.check_password(self.environment['TEACHER_PASSWORD']))

    def test_preserves_existing_password_without_reset(self):
        teacher = CTFUser.objects.create_user(
            username=self.environment['TEACHER_USERNAME'],
            password='ExistingPassword123!',
            role='student',
            is_staff=True,
            is_superuser=True,
        )

        self.run_command()
        teacher.refresh_from_db()

        self.assertTrue(teacher.check_password('ExistingPassword123!'))
        self.assertEqual(teacher.role, 'teacher')
        self.assertFalse(teacher.is_staff)
        self.assertFalse(teacher.is_superuser)

    def test_resets_existing_password_when_enabled(self):
        CTFUser.objects.create_user(
            username=self.environment['TEACHER_USERNAME'],
            password='ExistingPassword123!',
        )

        self.run_command(TEACHER_RESET_PASSWORD='true')

        teacher = CTFUser.objects.get(username=self.environment['TEACHER_USERNAME'])
        self.assertTrue(teacher.check_password(self.environment['TEACHER_PASSWORD']))


class CookieAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.password = 'SecurePassword123!'
        self.user = CTFUser.objects.create_user(
            username='cookie-user',
            email='cookie@example.com',
            password=self.password,
        )

    def csrf_headers(self):
        response = self.client.get('/api/users/csrf/')
        self.assertEqual(response.status_code, 200)
        return {'HTTP_X_CSRFTOKEN': self.client.cookies['csrftoken'].value}

    def test_login_sets_short_lived_httponly_session_without_token_body(self):
        response = self.client.post(
            '/api/users/login/',
            {'username': self.user.username, 'password': self.password},
            format='json',
            **self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('token', response.data)
        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)
        session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(session_cookie['httponly'])
        self.assertEqual(int(session_cookie['max-age']), settings.SESSION_COOKIE_AGE)
        self.assertEqual(self.client.get('/api/users/profile/').status_code, 200)

    def test_cookie_authenticated_unsafe_request_requires_csrf_header(self):
        login_response = self.client.post(
            '/api/users/login/',
            {'username': self.user.username, 'password': self.password},
            format='json',
            **self.csrf_headers(),
        )
        self.assertEqual(login_response.status_code, 200)

        denied = self.client.put('/api/users/profile/update/', {'nickname': 'Denied'}, format='json')
        self.assertEqual(denied.status_code, 403)

        allowed = self.client.put(
            '/api/users/profile/update/',
            {'nickname': 'Allowed'},
            format='json',
            **self.csrf_headers(),
        )
        self.assertEqual(allowed.status_code, 200)

    def test_logout_invalidates_session_cookie(self):
        login_response = self.client.post(
            '/api/users/login/',
            {'username': self.user.username, 'password': self.password},
            format='json',
            **self.csrf_headers(),
        )
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post('/api/users/logout/', format='json', **self.csrf_headers())
        self.assertEqual(response.status_code, 204)
        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]['max-age'], 0)
        self.assertEqual(self.client.get('/api/users/profile/').status_code, 403)
