from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from audit.models import AuditEvent, AuditLedgerEntry

from .access import COOKIE_NAME, build_access_cookie_value, build_access_url
from .container_audit import record_container_audit
from .models import Category, Challenge, ChallengeContainer
from .port_pool import PortPool


User = get_user_model()


class ComplianceCategoryTests(TestCase):
    """Compliance exercises should use the existing challenge category model."""

    def test_compliance_category_exists_from_migration(self):
        self.assertTrue(Category.objects.filter(name='Compliance').exists())

    def test_categories_api_exposes_compliance_category(self):
        response = APIClient().get('/api/challenges/categories/')

        self.assertEqual(response.status_code, 200)
        payload = response.data.get('results', response.data)
        names = {item['name'] for item in payload}
        self.assertIn('Compliance', names)

# Create your tests here.


class ContainerRuntimeConfigTests(TestCase):
    @override_settings(CONTAINER_PORT_MIN=18080, CONTAINER_PORT_MAX=18082)
    def test_port_pool_uses_settings_range(self):
        pool = PortPool()

        self.assertEqual(pool.start_port, 18080)
        self.assertEqual(pool.end_port, 18082)
        self.assertEqual(pool.total_ports, 3)

    @override_settings(
        CONTAINER_IMAGE_ALIASES={
            'ctf-platform/sql-injection-basics:latest': 'ctf-platform/sql-inject-basic:latest',
        }
    )
    def test_container_manager_resolves_image_aliases(self):
        from .container_manager import ContainerManager

        manager = ContainerManager.__new__(ContainerManager)

        self.assertEqual(
            manager._resolve_image_name('ctf-platform/sql-injection-basics:latest'),
            'ctf-platform/sql-inject-basic:latest',
        )
        self.assertEqual(
            manager._resolve_image_name('ctf-platform/sql-inject-basic:latest'),
            'ctf-platform/sql-inject-basic:latest',
        )

    def test_container_audit_writes_event_and_ledger(self):
        event, ledger = record_container_audit(
            action='start_failed',
            result='failed',
            challenge=None,
            image='missing:latest',
            error_message='docker image missing',
        )

        self.assertEqual(event.category, 'container')
        self.assertEqual(event.detail['action'], 'start_failed')
        self.assertEqual(event.detail['image'], 'missing:latest')
        self.assertEqual(ledger.event_category, 'container')
        self.assertEqual(ledger.payload['audit_event_id'], event.id)
        self.assertEqual(AuditEvent.objects.filter(category='container').count(), 1)
        self.assertEqual(AuditLedgerEntry.objects.filter(event_category='container').count(), 1)


class ChallengeProxyAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='proxy-owner', password='pass12345')
        category = Category.objects.create(name='Proxy Security')
        challenge = Challenge.objects.create(
            title='Proxy Lab',
            description='Authorized proxy test',
            category=category,
            difficulty='easy',
            score=100,
            flag='flag{proxy}',
            docker_image='ctf/proxy:latest',
        )
        self.container = ChallengeContainer.objects.create(
            user=self.user,
            challenge=challenge,
            container_id='proxy123',
            docker_container_name='proxy-container',
            status='running',
            port=18080,
            started_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.path = f'/challenge/{self.user.id}-{self.container.container_id}/'

    @patch('challenges.views.requests.request')
    def test_proxy_rejects_anonymous_request_without_scoped_cookie(self, request_mock):
        response = APIClient().get(self.path)

        self.assertEqual(response.status_code, 401)
        request_mock.assert_not_called()

    @patch('challenges.views.requests.request')
    def test_access_url_does_not_include_reusable_token(self, request_mock):
        access_url = build_access_url(self.container)

        self.assertNotIn('access_token=', access_url)
        self.assertEqual(access_url, f'http://localhost:8000{self.path}')
        request_mock.assert_not_called()

    @patch('challenges.views.requests.request')
    def test_proxy_accepts_scoped_cookie(self, request_mock):
        upstream = MagicMock()
        upstream.status_code = 200
        upstream.content = b'challenge ready'
        upstream.headers = {'content-type': 'text/plain'}
        upstream.encoding = 'utf-8'
        request_mock.return_value = upstream
        client = APIClient()
        client.cookies[COOKIE_NAME] = build_access_cookie_value(self.container)

        response = client.get(self.path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'challenge ready')
        self.assertNotIn(COOKIE_NAME, response.cookies)

    @patch('challenges.views.requests.request')
    def test_proxy_accepts_authenticated_owner_without_cookie(self, request_mock):
        upstream = MagicMock()
        upstream.status_code = 200
        upstream.content = b'challenge ready'
        upstream.headers = {'content-type': 'text/plain'}
        upstream.encoding = 'utf-8'
        request_mock.return_value = upstream
        token = Token.objects.create(user=self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        response = client.get(self.path)

        self.assertEqual(response.status_code, 200)
        request_mock.assert_called_once()

    @patch('challenges.views.requests.request')
    def test_proxy_rejects_cookie_for_another_container(self, request_mock):
        other = ChallengeContainer.objects.create(
            user=self.user,
            challenge=self.container.challenge,
            container_id='other123',
            docker_container_name='other-container',
            status='running',
            port=18081,
            started_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        client = APIClient()
        client.cookies[COOKIE_NAME] = build_access_cookie_value(other)

        response = client.get(self.path)

        self.assertEqual(response.status_code, 401)
        request_mock.assert_not_called()

    @patch('challenges.views.requests.request')
    def test_proxy_rejects_legacy_query_token(self, request_mock):
        response = APIClient().get(f'{self.path}?access_token=legacy-token')

        self.assertEqual(response.status_code, 401)
        request_mock.assert_not_called()

    @patch('challenges.views.requests.request')
    def test_proxy_rejects_unsafe_session_request_without_csrf(self, request_mock):
        client = APIClient(enforce_csrf_checks=True)
        self.assertTrue(client.login(username=self.user.username, password='pass12345'))

        response = client.post(self.path, data=b'payload', content_type='text/plain')

        self.assertEqual(response.status_code, 403)
        request_mock.assert_not_called()

    @patch('challenges.views.requests.request')
    def test_proxy_rejects_authenticated_non_owner(self, request_mock):
        other_user = User.objects.create_user(username='proxy-other', password='pass12345')
        token = Token.objects.create(user=other_user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        response = client.get(self.path)

        self.assertEqual(response.status_code, 403)
        request_mock.assert_not_called()

    @patch('challenges.views.requests.request')
    def test_proxy_preserves_safe_request_data_and_filters_sensitive_headers(self, request_mock):
        upstream = MagicMock()
        upstream.status_code = 200
        upstream.content = b'challenge ready'
        upstream.headers = {'content-type': 'text/plain'}
        upstream.encoding = 'utf-8'
        request_mock.return_value = upstream
        client = APIClient()
        client.cookies[COOKIE_NAME] = build_access_cookie_value(self.container)
        token = Token.objects.create(user=self.user)

        response = client.post(
            f'{self.path}?mode=practice&access_token=legacy-token',
            data=b'payload',
            content_type='text/plain',
            HTTP_AUTHORIZATION=f'Token {token.key}',
            HTTP_REFERER='https://example.test/private',
            HTTP_X_TRACE_ID='trace-1',
        )

        self.assertEqual(response.status_code, 200)
        kwargs = request_mock.call_args.kwargs
        self.assertEqual(kwargs['method'], 'POST')
        self.assertTrue(kwargs['url'].endswith('/?mode=practice'))
        self.assertEqual(kwargs['headers']['X-TRACE-ID'], 'trace-1')
        self.assertNotIn('Authorization', kwargs['headers'])
        self.assertNotIn('Cookie', kwargs['headers'])
        self.assertNotIn('Referer', kwargs['headers'])

    @patch('challenges.views.get_container_manager')
    def test_authenticated_container_action_sets_scoped_http_only_cookie(self, manager_factory):
        token = Token.objects.create(user=self.user)
        manager_factory.return_value.get_container_status.return_value = self.container
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        response = client.get(f'/api/challenges/challenges/{self.container.challenge_id}/container/')

        self.assertEqual(response.status_code, 200)
        cookie = response.cookies[COOKIE_NAME]
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['path'], self.path)


class ContainerIsolationTests(TestCase):
    @override_settings(CONTAINER_PROXY_MODE='host_port')
    def test_container_start_keeps_isolation_and_resource_limits(self):
        from .container_manager import ContainerManager

        user = User.objects.create_user(username='isolation-user', password='pass12345')
        category = Category.objects.create(name='Isolation Security')
        challenge = Challenge.objects.create(
            title='Isolation Lab',
            description='Container isolation test',
            category=category,
            difficulty='easy',
            score=100,
            flag='flag{isolation}',
            docker_image='ctf/isolation:latest',
            redirect_port=8080,
        )
        manager = ContainerManager.__new__(ContainerManager)
        manager.docker_client = MagicMock()
        manager.port_pool = MagicMock()
        manager.port_pool.allocate_port.return_value = 18080
        manager.network_name = 'ctf-challenge'
        manager.container_lifetime = 7200
        manager.cpu_limit = 0.5
        manager.memory_limit = '512m'
        manager.run_user = '65532:65532'
        manager._is_docker_available = MagicMock(return_value=True)
        manager.get_docker_image_status = MagicMock(return_value=True)
        manager._audit_container_action = MagicMock()

        success, _, container = manager.start_container(user, challenge)

        self.assertTrue(success)
        self.assertIsNotNone(container)
        run_kwargs = manager.docker_client.containers.run.call_args.kwargs
        self.assertEqual(run_kwargs['network'], 'ctf-challenge')
        self.assertEqual(run_kwargs['ports'], {8080: ('127.0.0.1', 18080)})
        self.assertEqual(run_kwargs['mem_limit'], '512m')
        self.assertEqual(run_kwargs['cpu_quota'], 50000)
        self.assertEqual(run_kwargs['pids_limit'], 256)
        self.assertEqual(run_kwargs['cap_drop'], ['ALL'])
        self.assertEqual(run_kwargs['security_opt'], ['no-new-privileges:true'])
        self.assertEqual(run_kwargs['user'], '65532:65532')
        self.assertTrue(run_kwargs['read_only'])
        self.assertEqual(run_kwargs['tmpfs'], {
            '/tmp': 'rw,noexec,nosuid,size=64m',
            '/run': 'rw,noexec,nosuid,size=16m',
            '/var/tmp': 'rw,noexec,nosuid,size=32m',
        })
        self.assertFalse(run_kwargs['privileged'])
        audit_kwargs = manager._audit_container_action.call_args.kwargs
        self.assertEqual(audit_kwargs['action'], 'start_succeeded')
        self.assertEqual(audit_kwargs['network'], 'ctf-challenge')
        self.assertEqual(audit_kwargs['cpu_limit'], 0.5)
        self.assertEqual(audit_kwargs['memory_limit'], '512m')


class FRPClientManagerSecurityTests(TestCase):
    @override_settings(FRP_TOKEN='')
    @patch('challenges.frp_client_manager.docker.from_env')
    def test_sidecar_does_not_start_without_configured_token(self, docker_from_env):
        from .frp_client_manager import FRPClientManager

        manager = FRPClientManager()

        self.assertFalse(manager.start_frpc_sidecar(MagicMock()))
        docker_from_env.return_value.images.get.assert_not_called()
