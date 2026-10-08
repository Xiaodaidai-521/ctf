import os
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import MagicMock, patch

import docker
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
import requests

from .access import build_access_url
from .container_manager import ContainerManager
from .juice_shop import JuiceShopRuntime, LABEL
from .models import Challenge, ChallengeContainer


class JuiceShopTests(TestCase):
    def setUp(self):
        call_command('import_juice_shop', verbosity=0)
        self.challenge = Challenge.objects.get(docker_image=settings.JUICE_SHOP_IMAGE)
        self.user = get_user_model().objects.create_user(username='juice-learner')

    def record(self, **kwargs):
        values = dict(
            user=self.user, challenge=self.challenge, container_id='unit-instance',
            docker_container_name='ctf-js-unit-instance', status='running', port=18080,
            access_url='http://127.0.0.1:18080/',
            runtime_metadata={'profile': 'juice-shop', 'network': 'ctf-js-unit-instance'},
            expires_at=timezone.now() + timedelta(hours=1),
        )
        values.update(kwargs)
        return ChallengeContainer.objects.create(**values)

    def test_import_is_idempotent_and_practice_cannot_score(self):
        call_command('import_juice_shop', verbosity=0)
        self.assertEqual(Challenge.objects.filter(docker_image=settings.JUICE_SHOP_IMAGE).count(), 1)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post(f'/api/challenges/challenges/{self.challenge.pk}/submit/', {'flag': 'anything'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.user.submission_set.exists())

    def test_direct_url_has_no_platform_access_token(self):
        record = self.record()
        self.assertEqual(build_access_url(record), record.access_url)
        record.expires_at = timezone.now() - timedelta(seconds=1)
        self.assertEqual(build_access_url(record), '')

    @patch('challenges.views.get_container_manager')
    def test_anonymous_start_identifies_missing_session_without_starting_docker(self, manager):
        response = APIClient().post(f'/api/challenges/challenges/{self.challenge.pk}/start/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'authentication_required')
        manager.assert_not_called()

    def test_permission_failures_are_not_marked_as_missing_login(self):
        from rest_framework.exceptions import PermissionDenied
        from ctf_backend.api_exceptions import api_exception_handler
        response = api_exception_handler(PermissionDenied('CSRF Failed'), {})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('code', response.data)

    @patch('challenges.views.get_container_manager', side_effect=docker.errors.DockerException('daemon offline'))
    def test_missing_docker_returns_actionable_503(self, manager):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post(f'/api/challenges/challenges/{self.challenge.pk}/start/')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Docker', str(response.data['detail']))

    def test_existing_environment_is_not_duplicated(self):
        self.record()
        client = MagicMock()
        ok, _, _ = JuiceShopRuntime(client).start(self.user, self.challenge)
        self.assertFalse(ok)
        client.networks.create.assert_not_called()

    def test_missing_container_still_removes_owned_network(self):
        record = self.record()
        client = MagicMock()
        client.containers.get.side_effect = docker.errors.NotFound('gone')
        network = client.networks.get.return_value
        network.attrs = {'Labels': {LABEL: record.container_id}}
        self.assertTrue(JuiceShopRuntime(client).stop(record))
        network.remove.assert_called_once()
        record.refresh_from_db()
        self.assertEqual(record.status, 'stopped')
        self.assertEqual(record.access_url, '')

    def test_cleanup_refuses_unowned_container(self):
        record = self.record()
        client = MagicMock()
        client.containers.get.return_value.labels = {}
        self.assertFalse(JuiceShopRuntime(client).stop(record))
        client.containers.get.return_value.remove.assert_not_called()
        client.networks.get.assert_not_called()

    def test_start_failure_rolls_back_container_and_network(self):
        client = MagicMock()
        client.containers.get.return_value.labels = {}
        with patch.object(JuiceShopRuntime, '_create', side_effect=RuntimeError('simulated failure')):
            # The failing creation has not created a Docker container.
            client.containers.get.side_effect = docker.errors.NotFound('gone')
            client.networks.get.side_effect = lambda name: self._network(name)
            ok, _, _ = JuiceShopRuntime(client).start(self.user, self.challenge)
        self.assertFalse(ok)
        record = ChallengeContainer.objects.get(user=self.user)
        self.assertEqual(record.status, 'error')
        self.assertIsNotNone(record.destroyed_at)

    def _network(self, name):
        network = MagicMock()
        network.attrs = {'Labels': {LABEL: name.removeprefix('ctf-js-')}}
        return network

    def test_cleanup_dry_run_does_not_destroy_and_real_run_routes_runtime(self):
        self.record(expires_at=timezone.now() - timedelta(seconds=1))
        manager = ContainerManager.__new__(ContainerManager)
        manager._audit_container_action = MagicMock()
        with patch.object(manager, 'stop_container', return_value=True) as stop:
            self.assertEqual(manager.cleanup_expired_containers(dry_run=True), 1)
            stop.assert_not_called()
            self.assertEqual(manager.cleanup_expired_containers(), 1)
            stop.assert_called_once()


@skipUnless(os.environ.get('RUN_JUICE_DOCKER_TESTS') == '1', 'requires the pinned local Docker image')
class JuiceShopDockerIntegrationTests(TestCase):
    def test_api_lifecycle_isolation_reset_and_expiration(self):
        call_command('import_juice_shop', verbosity=0)
        challenge = Challenge.objects.get(docker_image=settings.JUICE_SHOP_IMAGE)
        owner = get_user_model().objects.create_user(username='juice-integration-owner')
        other = get_user_model().objects.create_user(username='juice-integration-other')
        client = APIClient()
        client.force_authenticate(owner)
        second = APIClient()
        second.force_authenticate(other)
        docker_client = docker.from_env()
        runtime = JuiceShopRuntime(docker_client)
        base = f'/api/challenges/challenges/{challenge.pk}/'
        try:
            first = client.post(base + 'start/')
            self.assertEqual(first.status_code, 200, first.data)
            response = requests.get(first.data['container']['access_url'], timeout=10)
            self.assertEqual(response.status_code, 200)
            record = ChallengeContainer.objects.get(user=owner, status='running')
            self.assertEqual(second.post(base + 'stop/').status_code, 404)
            self.assertEqual(client.post(base + 'start/').status_code, 400)
            second_start = second.post(base + 'start/')
            self.assertEqual(second_start.status_code, 200, second_start.data)
            second_record = ChallengeContainer.objects.get(user=other, status='running')
            self.assertNotEqual(record.port, second_record.port)
            self.assertNotEqual(record.runtime_metadata['network'], second_record.runtime_metadata['network'])
            for item in (record, second_record):
                network = docker_client.networks.get(item.runtime_metadata['network'])
                self.assertEqual(network.attrs['Driver'], 'bridge')
                self.assertEqual(len(network.attrs['Containers']), 1)
                product_data = requests.get(item.access_url + 'rest/products/search?q=', timeout=10).json()
                self.assertEqual(product_data['status'], 'success')
                self.assertGreater(len(product_data['data']), 0)
            self.assertEqual(client.post(base + 'stop/').status_code, 200)
            with self.assertRaises(docker.errors.NotFound):
                docker_client.networks.get(record.runtime_metadata['network'])
            restart = client.post(base + 'start/')
            self.assertEqual(restart.status_code, 200, restart.data)
            replacement = ChallengeContainer.objects.get(user=owner, status='running')
            self.assertNotEqual(replacement.docker_container_name, record.docker_container_name)
            replacement.expires_at = timezone.now() - timedelta(seconds=1)
            replacement.save()
            call_command('cleanup_containers')
            replacement.refresh_from_db()
            self.assertEqual(replacement.status, 'stopped')
            with self.assertRaises(docker.errors.NotFound):
                docker_client.containers.get(replacement.docker_container_name)
        finally:
            for item in ChallengeContainer.objects.filter(user__in=[owner, other]):
                runtime.stop(item)
            docker_client.close()
