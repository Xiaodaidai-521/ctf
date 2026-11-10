"""Request propagation at the remaining user serializer boundaries."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from data_security.adapters.persistence.fields import bind_field_storage
from .models import CTFUser
from .serializers import AdminUserCreateSerializer, AdminUserUpdateSerializer, UserSerializer


class UserRequestContextTests(TestCase):
    def setUp(self):
        bind_field_storage(None)
        self.addCleanup(bind_field_storage, None)
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = CTFUser.objects.create_user(username='context-subject', email='Subject@example.invalid')
        self.admin = CTFUser.objects.create_user(username='context-admin', role='admin')

    def test_registration_and_login_responses_use_the_server_request(self):
        password = 'Synthetic-context-passphrase-47!'
        registration = {'username': 'context-register', 'email': 'Register@example.invalid',
                        'password': password, 'password2': password}
        cases = (('register', registration, 201),
                 ('login', {'username': registration['username'], 'password': password}, 200))
        for endpoint, data, expected in cases:
            with self.subTest(endpoint=endpoint):
                self.client.get('/api/users/csrf/')
                with patch('users.views.UserSerializer', wraps=UserSerializer) as serializer:
                    response = self.client.post(f'/api/users/{endpoint}/', data, format='json',
                        HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
                self.assertEqual(response.status_code, expected)
                self.assertEqual(serializer.call_count, 1)
                request = serializer.call_args.kwargs['context']['request']
                self.assertIs(request._request, response.wsgi_request)
                self.assertEqual(request.user.pk, response.data['user']['id'])
                self.assertEqual(response.data['user']['email'], registration['email'])

    def test_resource_review_passes_request_to_nested_users_without_unmasking(self):
        from ctf_backend.security_bootstrap import assemble
        from data_security.tests.phase4_fixtures import field_configuration
        from resources.models import Resource

        self.admin.is_staff = True
        self.admin.email = 'Admin@example.invalid'
        self.admin.save(update_fields=['is_staff', 'email'])
        self.client.force_authenticate(self.admin)
        resource = Resource.objects.create(title='Synthetic context resource', resource_type='document',
            uploader=self.user, file='synthetic/no-file-is-created.txt')
        with field_configuration(legacy_reads=True) as (path, *_):
            components = assemble(config_path=path)
            for bound in (False, True):
                with self.subTest(bound=bound):
                    bind_field_storage(components['fields'] if bound else None)
                    with patch.object(UserSerializer, 'to_representation', autospec=True,
                                      side_effect=UserSerializer.to_representation) as nested:
                        response = self.client.post('/api/resources/review/',
                            {'resource_id': resource.pk, 'status': 'approved'}, format='json')
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(nested.call_count, 2)
                    for call in nested.call_args_list:
                        request = call.args[0].context['request']
                        self.assertIs(request._request, response.wsgi_request)
                        self.assertEqual(request.user.pk, self.admin.pk)
                    payload = response.data['resource']
                    self.assertEqual(payload['uploader_info']['email'], '[REDACTED]' if bound else self.user.email)
                    self.assertEqual(payload['reviewer_info']['email'], '[REDACTED]' if bound else self.admin.email)
                    self.assertEqual(payload['file_url'], f'http://testserver/api/resources/{resource.pk}/download/')

    def test_profile_read_and_update_use_the_server_request(self):
        self.client.force_authenticate(self.user)
        cases = ((self.client.get, '/api/users/profile/', {}),
                 (self.client.put, '/api/users/profile/update/', {'nickname': 'Synthetic subject'}))
        for method, url, data in cases:
            with self.subTest(url=url), patch('users.views.UserSerializer', wraps=UserSerializer) as serializer:
                response = method(url, data, format='json')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(serializer.call_count, 1)
                request = serializer.call_args.kwargs['context']['request']
                self.assertIs(request._request, response.wsgi_request)
                self.assertEqual(request.user.pk, self.user.pk)
                payload = response.data.get('user', response.data)
                self.assertEqual(payload['email'], self.user.email)

    def test_admin_list_create_and_update_pass_request_to_input_and_output(self):
        self.client.force_authenticate(self.admin)
        with (
            patch('users.views.UserSerializer', wraps=UserSerializer) as output,
            patch('users.views.AdminUserCreateSerializer', wraps=AdminUserCreateSerializer) as create,
            patch('users.views.AdminUserUpdateSerializer', wraps=AdminUserUpdateSerializer) as update,
        ):
            cases = (
                (self.client.get, '/api/users/admin/users/', {}, 200, None),
                (self.client.post, '/api/users/admin/users/create/',
                 {'username': 'context-created', 'email': 'Created@example.invalid',
                  'password': 'Synthetic-created-passphrase-68!'}, 201, create),
                (self.client.patch, f'/api/users/admin/users/{self.user.pk}/update/',
                 {'nickname': 'Synthetic updated'}, 200, update),
            )
            for method, url, data, expected, input_serializer in cases:
                with self.subTest(url=url):
                    output.reset_mock()
                    response = method(url, data, format='json')
                    self.assertEqual(response.status_code, expected)
                    for serializer in (output,) if input_serializer is None else (input_serializer, output):
                        self.assertEqual(serializer.call_count, 1)
                        request = serializer.call_args.kwargs['context']['request']
                        self.assertIs(request._request, response.wsgi_request)
                        self.assertEqual(request.user.pk, self.admin.pk)
