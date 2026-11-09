"""Synthetic-only credential acceptance; run on the isolated PostgreSQL cluster."""
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.hashers import (
    PBKDF2PasswordHasher, PBKDF2SHA1PasswordHasher, get_hasher, identify_hasher,
)
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient, APIRequestFactory

from challenges.coze_injector import get_coze_sdk_script, inject_coze_sdk
from challenges.models import Category, Challenge, ChallengeContainer
from challenges.views import ProxySessionAuthentication, proxy_challenge_view
from data_security.adapters.django import authentication as boundary
from users.models import CTFUser
from users.serializers import AdminUserCreateSerializer, UserRegisterSerializer
from users.views import profile_view


PASSWORD = 'Synthetic-River-7!Cedar'
REPLACEMENT = 'Synthetic-Cobalt-9!Birch'


class BootstrapCredentialTests(TestCase):
    def setUp(self):
        loader = patch.object(boundary, '_bootstrap_loader', None)
        loader.start()
        self.addCleanup(loader.stop)
        self.inputs = {'username': 'phase3-bootstrap', 'email': 'bootstrap@example.invalid',
                       'password': PASSWORD, 'reset_password': False}
        boundary.bind_bootstrap_teacher_inputs(lambda: self.inputs)

    def test_explicit_password_creates_salted_nonprivileged_teacher(self):
        output = StringIO()
        call_command('bootstrap_teacher', stdout=output)
        teacher = CTFUser.objects.get(username=self.inputs['username'])
        self.assertTrue(teacher.check_password(PASSWORD))
        self.assertNotEqual(teacher.password, PASSWORD)
        self.assertEqual(teacher.role, 'teacher')
        self.assertFalse(teacher.is_staff or teacher.is_superuser)
        self.assertNotIn(PASSWORD, output.getvalue())

    def test_no_default_password_or_partial_user_on_failure(self):
        for password in (None, '', '123456'):
            with self.subTest(missing=password is None):
                self.inputs['password'] = password
                with self.assertRaises(CommandError):
                    call_command('bootstrap_teacher', stdout=StringIO())
                self.assertFalse(CTFUser.objects.filter(username=self.inputs['username']).exists())

    def test_unbound_refuses_instead_of_reading_environment(self):
        boundary.bind_bootstrap_teacher_inputs(None)
        with self.assertRaisesRegex(CommandError, 'TEACHER_BOOTSTRAP_NOT_BOUND'):
            call_command('bootstrap_teacher', stdout=StringIO())
        self.assertFalse(CTFUser.objects.exists())

    def test_formal_injection_does_not_consume_legacy_environment(self):
        with patch('os.getenv', side_effect=AssertionError('ENV_READ_FORBIDDEN')), \
                patch('os.environ.get', side_effect=AssertionError('ENV_READ_FORBIDDEN')):
            self.assertIs(boundary.bootstrap_teacher_inputs(), self.inputs)

    def test_existing_hash_preserved_without_reset_and_weak_reset_is_atomic(self):
        teacher = CTFUser.objects.create_user(username=self.inputs['username'], password=PASSWORD,
                                              role='admin', is_staff=True)
        old_hash = teacher.password
        self.inputs['password'] = None
        call_command('bootstrap_teacher', stdout=StringIO())
        teacher.refresh_from_db()
        self.assertEqual(teacher.password, old_hash)
        teacher.role = 'admin'
        teacher.save(update_fields=['role'])
        self.inputs.update(reset_password=True, password='123456')
        with self.assertRaisesRegex(CommandError, 'TEACHER_PASSWORD_REJECTED'):
            call_command('bootstrap_teacher', stdout=StringIO())
        teacher.refresh_from_db()
        self.assertEqual(teacher.role, 'admin')
        self.assertEqual(teacher.password, old_hash)

    def test_explicit_reset_uses_validated_new_hash(self):
        teacher = CTFUser.objects.create_user(username=self.inputs['username'], password=PASSWORD)
        self.inputs.update(reset_password=True, password=REPLACEMENT)
        call_command('bootstrap_teacher', stdout=StringIO())
        teacher.refresh_from_db()
        self.assertTrue(teacher.check_password(REPLACEMENT))
        self.assertFalse(teacher.check_password(PASSWORD))


class PasswordValidationTests(TestCase):
    def test_registration_and_admin_create_validate_all_configured_rules(self):
        for serializer_type in (UserRegisterSerializer, AdminUserCreateSerializer):
            for password in ('short', 'password', '923487129384', 'phase3-person'):
                with self.subTest(serializer=serializer_type.__name__, rule=password):
                    data = {'username': 'phase3-person', 'email': 'person@example.invalid', 'password': password}
                    if serializer_type is UserRegisterSerializer:
                        data['password2'] = password
                    serializer = serializer_type(data=data)
                    self.assertFalse(serializer.is_valid())
        self.assertFalse(CTFUser.objects.exists())

    def test_registration_preserves_distinct_salts_and_hides_password_fields(self):
        users = []
        for username in ('phase3-one', 'phase3-two'):
            serializer = UserRegisterSerializer(data={'username': username, 'password': PASSWORD,
                                                     'password2': PASSWORD})
            self.assertTrue(serializer.is_valid(), serializer.errors)
            users.append(serializer.save())
            self.assertNotIn('password', serializer.data)
            self.assertNotIn('password2', serializer.data)
        self.assertNotEqual(users[0].password, users[1].password)
        for user in users:
            self.assertTrue(user.check_password(PASSWORD))
            self.assertEqual(identify_hasher(user.password).algorithm, 'pbkdf2_sha256')
        self.assertNotEqual(users[0].password.split('$')[2], users[1].password.split('$')[2])

    def test_self_change_requires_old_password_and_validates_before_write(self):
        user = CTFUser.objects.create_user(username='phase3-self', password=PASSWORD)
        old_hash = user.password
        client = APIClient()
        client.force_authenticate(user)
        for body in ({'password': REPLACEMENT}, {'password': REPLACEMENT, 'old_password': 'wrong'},
                     {'password': '123456', 'old_password': PASSWORD}):
            self.assertEqual(client.put('/api/users/profile/update/', body, format='json').status_code, 400)
            user.refresh_from_db()
            self.assertEqual(user.password, old_hash)

    def test_admin_create_and_reset_validate_and_never_return_password(self):
        admin = CTFUser.objects.create_user(username='phase3-admin', password=PASSWORD, role='admin')
        user = CTFUser.objects.create_user(username='phase3-target', password=PASSWORD)
        client = APIClient()
        client.force_authenticate(admin)
        response = client.post('/api/users/admin/users/create/',
                               {'username': 'phase3-created', 'password': '123456'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CTFUser.objects.filter(username='phase3-created').exists())
        response = client.post('/api/users/admin/users/create/',
                               {'username': 'phase3-created', 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('password', response.data['user'])
        url = f'/api/users/admin/users/{user.pk}/update/'
        old_hash = user.password
        self.assertEqual(client.patch(url, {'password': '123456'}, format='json').status_code, 400)
        user.refresh_from_db()
        self.assertEqual(user.password, old_hash)
        response = client.patch(url, {'password': REPLACEMENT}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('password', response.data['user'])
        user.refresh_from_db()
        self.assertTrue(user.check_password(REPLACEMENT))

    def test_self_change_preserves_current_session_but_invalidates_other_session(self):
        user = CTFUser.objects.create_user(username='phase3-sessions', password=PASSWORD)
        current, other = APIClient(enforce_csrf_checks=True), APIClient()
        for client in (current, other):
            client.force_login(user)
        current.get('/api/users/csrf/')
        body = {'old_password': PASSWORD, 'password': REPLACEMENT}
        self.assertEqual(current.put('/api/users/profile/update/', body, format='json').status_code, 403)
        response = current.put('/api/users/profile/update/', body, format='json',
                               HTTP_X_CSRFTOKEN=current.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('password', response.data['user'])
        self.assertNotIn('old_password', response.data['user'])
        self.assertEqual(current.get('/api/users/profile/').status_code, 200)
        self.assertEqual(other.get('/api/users/profile/').status_code, 403)
        user.refresh_from_db()
        self.assertTrue(user.check_password(REPLACEMENT))

    def test_regular_user_cannot_admin_reset_another_user(self):
        user = CTFUser.objects.create_user(username='phase3-student', password=PASSWORD)
        target = CTFUser.objects.create_user(username='phase3-admin-target', password=PASSWORD)
        client = APIClient()
        client.force_authenticate(user)
        response = client.patch(f'/api/users/admin/users/{target.pk}/update/',
                                {'password': REPLACEMENT}, format='json')
        self.assertEqual(response.status_code, 403)
        target.refresh_from_db()
        self.assertTrue(target.check_password(PASSWORD))

    def test_actual_default_hasher_cost_and_login_upgrades_old_hashes(self):
        hasher = get_hasher()
        self.assertEqual(hasher.algorithm, 'pbkdf2_sha256')
        self.assertEqual(hasher.iterations, PBKDF2PasswordHasher.iterations)
        self.assertGreaterEqual(hasher.iterations, 1_000_000)
        for index, old_hasher in enumerate((PBKDF2PasswordHasher(), PBKDF2SHA1PasswordHasher())):
            user = CTFUser.objects.create_user(username=f'phase3-upgrade-{index}')
            user.password = old_hasher.encode(PASSWORD, 'syntheticoldsalt', iterations=1000)
            user.save(update_fields=['password'])
            old_hash = user.password
            client = APIClient(enforce_csrf_checks=True)
            client.get('/api/users/csrf/')
            response = client.post('/api/users/login/', {'username': user.username, 'password': PASSWORD},
                                   format='json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
            self.assertEqual(response.status_code, 200)
            user.refresh_from_db()
            self.assertNotEqual(user.password, old_hash)
            self.assertEqual(identify_hasher(user.password).algorithm, hasher.algorithm)
            self.assertEqual(int(user.password.split('$')[1]), hasher.iterations)
            self.assertTrue(user.check_password(PASSWORD))


class DisabledTokenAndCozeUnitTests(SimpleTestCase):
    def test_password_similarity_uses_new_username_during_profile_update(self):
        from django.core.exceptions import ValidationError
        from users.serializers import UserSerializer
        user = CTFUser(username='previous-name')
        serializer = UserSerializer(instance=user)
        with patch.object(user, 'check_password', return_value=True):
            with self.assertRaises(ValidationError):
                serializer.validate({'username': 'Synthetic-Cedar-Username',
                                     'password': 'Synthetic-Cedar-Username',
                                     'old_password': PASSWORD})

    def test_disabled_token_does_not_access_token_model_or_echo_credential(self):
        auth = boundary.DisabledTokenAuthentication()
        factory = APIRequestFactory()
        for value in ('Token synthetic-never-issued', 'TOKEN', 'token malformed extra'):
            with self.assertRaises(AuthenticationFailed) as error:
                auth.authenticate(factory.get('/', HTTP_AUTHORIZATION=value))
            self.assertEqual(str(error.exception), 'TOKEN_AUTHENTICATION_DISABLED')
        self.assertIsNone(auth.authenticate(factory.get('/')))
        self.assertIsNone(auth.authenticate(factory.get('/', HTTP_AUTHORIZATION='Bearer unrelated')))

    @override_settings(COZE_SDK_ENABLED=True, COZE_TOKEN='synthetic-never-issued-coze',
                       COZE_BOT_ID='synthetic-bot', COZE_WIDGET_TITLE='synthetic-title')
    def test_old_coze_switch_cannot_reenable_browser_injection(self):
        for html in ('<html><body>synthetic page</body></html>', '<div>no body</div>'):
            self.assertEqual(get_coze_sdk_script(), '')
            self.assertEqual(inject_coze_sdk(html), html)
            self.assertNotIn('synthetic-never-issued-coze', inject_coze_sdk(html))


class FormalTokenClosureTests(TestCase):
    def setUp(self):
        self.user = CTFUser.objects.create_user(username='phase3-token-owner', password=PASSWORD)
        self.token = Token.objects.create(user=self.user)
        category = Category.objects.create(name='Synthetic phase3 credential tests')
        challenge = Challenge.objects.create(title='Synthetic page', description='Synthetic only',
            category=category, difficulty='easy', score=10, flag='synthetic-only', docker_image='synthetic:never-run')
        self.container = ChallengeContainer.objects.create(user=self.user, challenge=challenge,
            container_id='phase3synthetic', docker_container_name='synthetic-never-run', status='running',
            port=18080, started_at=timezone.now(), expires_at=timezone.now() + timedelta(hours=1))
        self.path = f'/challenge/{self.user.pk}-{self.container.container_id}/'

    def test_synthetic_inventory_exposes_legacy_plaintext_and_default_compatibility(self):
        # This is only our freshly created row, not a production inventory query.
        self.assertEqual(Token.objects.get(pk=self.token.pk).key, self.token.key)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.assertEqual(client.get('/api/users/profile/').status_code, 200)

    def test_explicit_formal_closure_denies_existing_token_without_database_lookup(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        with patch.object(profile_view.cls, 'authentication_classes',
                          [SessionAuthentication, boundary.DisabledTokenAuthentication]), \
                patch.object(proxy_challenge_view.cls, 'authentication_classes',
                             [ProxySessionAuthentication, boundary.DisabledTokenAuthentication]), \
                patch('challenges.views.requests.request') as send:
            with self.assertNumQueries(0):
                self.assertEqual(client.get('/api/users/profile/').status_code, 403)
                self.assertEqual(client.get(self.path).status_code, 403)
            send.assert_not_called()
            self.token.delete()  # Synthetic row only: closure is independent of retained legacy stock.
            self.assertEqual(client.get('/api/users/profile/').status_code, 403)

    @override_settings(COZE_SDK_ENABLED=True, COZE_TOKEN='synthetic-browser-forbidden')
    def test_formal_session_proxy_still_works_without_coze_injection(self):
        upstream = MagicMock(status_code=200, content=b'<html><body>synthetic page</body></html>',
                             headers={'content-type': 'text/html'}, encoding='utf-8')
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        with patch.object(proxy_challenge_view.cls, 'authentication_classes',
                          [ProxySessionAuthentication, boundary.DisabledTokenAuthentication]), \
                patch('challenges.views.requests.request', return_value=upstream) as send:
            response = client.get(self.path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, upstream.content)
            self.assertNotIn(b'synthetic-browser-forbidden', response.content)
            self.assertEqual(client.post(self.path, {'synthetic': 'body'}).status_code, 403)
            self.assertEqual(send.call_count, 1)
