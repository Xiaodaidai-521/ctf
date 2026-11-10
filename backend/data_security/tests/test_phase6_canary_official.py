"""Actual adapter boundary with synthetic owners and transport-only captures."""
import json
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from data_security.adapters.llm.official import ENDPOINTS
from data_security.application.canary import CanaryTools
from data_security.contracts import AIResponse, EmbeddingResult, Outlet, ProtectionError, ReasonCode
from data_security.tests import test_phase3_official as official
from data_security.tests.test_phase6_canary import CanaryToolFixture


class CanaryOfficialTests(CanaryToolFixture, TestCase):
    adapter = official.OfficialTests.adapter
    request = official.OfficialTests.request
    wire = official.OfficialTests.wire

    def setUp(self):
        super().setUp()
        official.OfficialTests.setUp(self)
        self.seed = replace(self.seed, environment=self.context.environment, domain=self.context.domain)
        self.service = CanaryTools(**dict(self.options, seeds=(self.seed,),
            environment=self.context.environment, domain=self.context.domain, policy_binding=self.binding))
        # Planting persistence is still a synthetic owner, not a business ACL.
        self.values = self.service.catalog[self.seed.seed_id][1].tree.to_value()['values']
        self.checker = Mock(wraps=self.service)

    def test_all_official_bodies_are_checked_after_protection_before_authentication(self):
        test = self
        sent = []
        def capture(session, prepared, **kwargs):
            if '/oauth/' not in prepared.url:
                sent.append(json.loads(prepared.body))
            return self.wire(session, prepared, **kwargs)
        class Socket:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def send(self, value):
                body = json.loads(value)
                test.assertIn('header', body)
                body.pop('header')
                sent.append(body)
            def recv(self, **kwargs):
                return json.dumps({'header': {'code': 0}, 'payload': {'choices':
                    {'text': [{'content': 'safe'}], 'status': 2}}})
        with patch.object(requests.Session, 'send', autospec=True, side_effect=capture), \
                patch('data_security.adapters.llm.official.connect', return_value=Socket()):
            for name in ENDPOINTS:
                for mode in ('chat', 'stream'):
                    with self.subTest(provider=name, mode=mode):
                        adapter = self.adapter(name)
                        adapter.canary = self.checker
                        request = self.request(name, {'messages': [{'role': 'user',
                            'content': ' '.join(self.values.values())}]})
                        result = getattr(adapter, mode)(request, self.context, self.binding)
                        if mode == 'stream':
                            result = list(result)[0]
                        self.assertIsInstance(result, AIResponse)
                        checked = self.checker.check.call_args.kwargs
                        self.assertEqual(checked['payload'].tree.to_value(), sent[-1])
                        self.assertEqual(checked['context'], self.context)
                        for literal in self.values.values():
                            self.assertFalse(literal in json.dumps(sent[-1]))
        self.assertEqual(self.checker.check.call_count, 12)
        self.assertEqual(len(sent), 12)
        self.assertEqual(self.events, [])

    def test_embedding_checks_the_actual_protected_input(self):
        with patch.object(requests.Session, 'send', autospec=True, side_effect=self.wire):
            for name in ('volcano', 'qwen'):
                adapter = self.adapter(name)
                adapter.canary = self.checker
                context = replace(self.context, outlet=Outlet.EMBEDDING)
                request = self.request(name, {'input': list(self.values.values())}, embedding=True)
                result = adapter.embed(request, context, self.binding)
                self.assertIsInstance(result, EmbeddingResult)
                checked = self.checker.check.call_args.kwargs
                self.assertEqual(checked['context'], context)
                self.assertEqual(checked['payload'].tree.to_value(), json.loads(self.captures[-1].body))
                for literal in self.values.values():
                    self.assertFalse(literal in self.captures[-1].body.decode())
        self.assertEqual(self.checker.check.call_count, 2)
        self.assertEqual(self.events, [])

    def test_fault_injected_literal_alerts_and_stops_before_keys_or_any_transport(self):
        with patch.object(requests.Session, 'send') as send, \
                patch('data_security.adapters.llm.official.connect') as connect, \
                patch.object(self.keys, 'resolve') as resolve:
            for name in ENDPOINTS:
                modes = ('chat', 'stream', 'embed') if name in ('volcano', 'qwen') else ('chat', 'stream')
                for mode in modes:
                    with self.subTest(provider=name, mode=mode):
                        embedding = mode == 'embed'
                        context = replace(self.context, outlet=Outlet.EMBEDDING if embedding else Outlet.MODEL)
                        body = {'input': list(self.values.values())} if embedding else {
                            'messages': [{'role': 'user', 'content': ' '.join(self.values.values())}]}
                        adapter = self.adapter(name)
                        adapter.canary = self.checker
                        # Deliberately break the protection port, never the check or transport assertion.
                        with patch.object(adapter, '_protect', side_effect=lambda payload, *_: payload):
                            result = getattr(adapter, mode)(self.request(name, body, embedding), context, self.binding)
                            if mode == 'stream':
                                result = list(result)[0]
                        self.assertIsInstance(result, ProtectionError)
                        self.assertEqual(result.code, ReasonCode.SCOPE_INCOMPLETE)
                        self.assertEqual(self.events[-1].counts, (('hit', 3),))
                        self.assertIn('outlet/' + context.outlet.value, self.events[-1].algorithm_versions)
                        self.assertEqual(self.events[-1].correlation_ref, context.trace_id)
            send.assert_not_called()
            connect.assert_not_called()
            resolve.assert_not_called()
        self.assertEqual(len(self.events), 14)

    def test_check_error_exception_or_invalid_result_is_not_a_clean_check(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                  retryable=False, trace_id='canary/test')
        with patch.object(requests.Session, 'send') as send, patch.object(self.keys, 'resolve') as resolve:
            for value in (failure, None, False, RuntimeError('synthetic exception')):
                adapter = self.adapter('deepseek')
                adapter.canary = Mock()
                if isinstance(value, Exception):
                    adapter.canary.check.side_effect = value
                else:
                    adapter.canary.check.return_value = value
                result = adapter.chat(self.request('deepseek'), self.context, self.binding)
                self.assertIsInstance(result, ProtectionError)
                self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
            send.assert_not_called()
            resolve.assert_not_called()
