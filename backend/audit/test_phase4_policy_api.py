"""Synthetic previews have no request-body, secret, or raw-content endpoint."""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from ctf_backend.security_bootstrap import assemble
from data_security.adapters.django.policy_api import bind_policy_api, policies, preview
from data_security.contracts import PolicySnapshot, PolicyStatus
from data_security.tests.phase2_fixtures import MemoryAudit
from data_security.tests.phase3_fixtures import configuration


class PolicyAPITests(SimpleTestCase):
    def setUp(self):
        fixture = configuration(providers=())
        path, self.config, refs, self.secrets, binding = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.components = assemble(config_path=path)
        self.audit = MemoryAudit()
        self.audit.record = lambda event, durability: replace(
            self.audit.append(event, durability), stored_at=event.occurred_at)
        self.components['protection'].audit = self.audit
        bind_policy_api(catalog=self.components['catalog'], binding=binding,
            preview=self.components['preview'], key_metadata=self.components['key_metadata'])
        self.addCleanup(bind_policy_api)
        self.factory = APIRequestFactory()

    def request(self, view, *, role='admin', data=None, active=True):
        request = (self.factory.get('/api/data-security/policies/') if data is None else
                   self.factory.post('/api/data-security/preview/', data, format='json'))
        if role is not None:
            force_authenticate(request, user=SimpleNamespace(pk=17, role=role,
                is_active=active, is_authenticated=True))
        return view(request)

    def test_only_active_admin_can_access(self):
        for view, data in ((policies, None), (preview, {'case': 'mixed'})):
            for role in ('student', 'teacher', None):
                with self.subTest(view=view.__name__, role=role):
                    self.assertIn(self.request(view, role=role, data=data).status_code, (401, 403))
            self.assertEqual(self.request(view, data=data, active=False).status_code, 403)

    def test_all_three_synthetic_cases_and_combination_are_masked(self):
        for case in ('email', 'ipv4', 'card', 'mixed'):
            result = self.request(preview, data={'case': case})
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.data['synthetic_only'])
            self.assertEqual(result['Cache-Control'], 'no-store')
            for original in ('Student@Example.invalid', '192.0.2.42', '4111111111111111'):
                self.assertNotIn(original, json.dumps(result.data))
                self.assertNotIn(original, json.dumps([event.to_wire() for event in self.audit.events]))

    def test_arbitrary_body_and_forged_context_do_not_reach_protection(self):
        with patch('data_security.adapters.django.policy_api._binding',
                   (self.components['catalog'], self.components['binding'], None, ())):
            for data in ({'case': 'mixed', 'text': 'not-accepted'}, {'text': 'not-accepted'},
                         {'case': 'phone'}, {'case': 'email', 'role': 'service'}, {'case': ['email']}):
                self.assertEqual(self.request(preview, data=data).status_code, 400)
        self.assertEqual(self.audit.events, [])

    def test_metadata_never_contains_secret_material(self):
        result = self.request(policies)
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.data['reveal_enabled'])
        wire = json.dumps(result.data)
        for value in self.secrets.values():
            self.assertNotIn(value.hex(), wire)
        self.assertEqual({key['purpose'] for key in result.data['keys']},
                         {'enc-data', 'audit-auth', 'framework-signing'})

    def test_retirement_is_rechecked_before_preview(self):
        source = Path(self.config['policy_file'])
        snapshot = PolicySnapshot.from_json(source.read_bytes())
        source.write_text(json.dumps(replace(snapshot, status=PolicyStatus.RETIRED).to_wire()))
        self.assertEqual(self.request(preview, data={'case': 'mixed'}).status_code, 503)
        self.assertEqual(self.request(policies).status_code, 503)

    def test_unbound_endpoint_fails_closed(self):
        bind_policy_api()
        self.assertEqual(self.request(policies).status_code, 503)
        self.assertEqual(self.request(preview, data={'case': 'mixed'}).status_code, 503)
