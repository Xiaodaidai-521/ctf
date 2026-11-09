"""Real B, file keys/policy and PostgreSQL audit; only the final HTTP send is captured."""
import asyncio
import json
import os
import secrets
from pathlib import Path
from unittest.mock import patch

from django.test import TransactionTestCase
import requests

from ai_providers import Message
from ctf_backend.security_bootstrap import assemble, framework_startup
from data_security.contracts import ContractViolation, KeyStatus
from data_security.tests.phase3_fixtures import configuration
from .models import SecurityAuditRecord


class BootstrapTests(TransactionTestCase):
    def setUp(self):
        self.files = configuration(('deepseek', 'qwen'))
        self.path, self.config, self.refs, self.material, self.binding = self.files.__enter__()
        self.addCleanup(self.files.__exit__, None, None, None)
        self.sent = []

    def capture(self, session, prepared, **kwargs):
        self.assertGreater(SecurityAuditRecord.objects.count(), 0)
        self.sent.append(prepared)
        body = json.loads(prepared.body)
        self.assertNotIn('a@example.invalid', str(body))
        self.assertNotIn('4111111111111111', str(body))
        self.assertNotIn('192.0.2.1', str(body))
        self.assertIn(prepared.headers['Authorization'].encode()[7:], self.material.values())
        response = requests.Response()
        response.status_code = 200
        if prepared.url.endswith('/embeddings'):
            result = {'data': [{'index': i, 'embedding': [0.1, 0.2]} for i in range(len(body['input']))]}
        else:
            result = {'choices': [{'message': {'content': 'a@example.invalid safe response'}}], 'usage': {}}
        response._content = json.dumps(result).encode()
        response._content_consumed = True
        return response

    def test_real_composition_single_sequential_concurrent_and_embedding(self):
        components = assemble(config_path=self.path)
        manager = components['manager']
        messages = [Message(role='user', content='a@example.invalid 192.0.2.1 4111111111111111')]
        with patch.object(requests.Session, 'send', autospec=True, side_effect=self.capture):
            result = asyncio.run(manager.chat_single('analyst', messages))
            self.assertNotIn('@', result.content)
            self.assertFalse(hasattr(result, 'raw_response'))
            results = asyncio.run(manager.chat_sequential(['analyst', 'security'], messages))
            self.assertEqual(len(results), 2)
            results = asyncio.run(manager.chat_collaborative(['analyst', 'security'], messages))
            self.assertEqual(len(results), 2)
            embedding = manager.get_provider('qwen').embed(['a@example.invalid'], model='embedding-v1')
            self.assertEqual(len(embedding.vectors), 1)
        self.assertEqual(len(self.sent), 6)
        self.assertGreaterEqual(SecurityAuditRecord.objects.count(), 11)
        for handle in manager._instances.values():
            self.assertFalse(hasattr(handle, 'config'))
            self.assertFalse(hasattr(handle, '_client'))

    def test_real_composition_retries_reprotect_and_revocation_blocks(self):
        components = assemble(config_path=self.path)
        handle = components['manager'].get_provider('deepseek')
        messages = [Message(role='user', content='a@example.invalid')]
        with patch.object(requests.Session, 'send', autospec=True, side_effect=self.capture):
            asyncio.run(handle.chat(messages))
            first_count = SecurityAuditRecord.objects.count()
            asyncio.run(handle.chat(messages))
            self.assertGreater(SecurityAuditRecord.objects.count(), first_count)
            manifest = Path(self.config['key_manifest'])
            data = json.loads(manifest.read_bytes())
            for entry in data['entries']:
                if entry['reference']['key_ref'] == self.refs['deepseek'].key_ref:
                    entry['reference']['status'] = KeyStatus.RETIRED.value
            manifest.write_text(json.dumps(data))
            with self.assertRaises(RuntimeError):
                asyncio.run(handle.chat(messages))
        self.assertEqual(len(self.sent), 2)

    def test_assembly_rejects_test_ports_random_and_dynamic_paths(self):
        for name in ('keys', 'audit', 'policy'):
            with self.subTest(parameter=name), self.assertRaises(ContractViolation):
                assemble(config_path=self.path, **{name: object()})
        with self.assertRaises(ContractViolation):
            assemble(config_path=self.path, random_bytes=lambda count: b'x' * count)
        with self.assertRaises(ContractViolation), patch('secrets.token_bytes', lambda count: b'x' * count):
            assemble(config_path=self.path)
        self.config['implementation'] = 'data_security.tests.phase2_fixtures.FakeKeys'
        self.path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            assemble(config_path=self.path)

    def test_framework_secret_from_independent_ref_not_environment_fallback(self):
        with patch.dict(os.environ, {'DATA_SECURITY_CONFIG': str(self.path), 'SECRET_KEY': 'do-not-use'}):
            self.assertEqual(framework_startup().encode(), self.material['framework_key'])
            (self.path.parent / 'framework_key.key').unlink()
            with self.assertRaises(ContractViolation):
                framework_startup()

    def test_actual_django_startup_installs_formal_boundaries(self):
        import subprocess
        import sys
        from tools.data_security import isolation
        env = isolation.environment()
        env['DATA_SECURITY_CONFIG'] = str(self.path)
        env['DJANGO_SETTINGS_MODULE'] = 'tools.data_security.test_settings'
        code = '''
import sys,json
from pathlib import Path
sys.path[:0]=[str(Path.cwd()),str(Path.cwd()/'backend')]
import django
django.setup()
from ai_providers import get_manager
from rest_framework.views import APIView
from rest_framework.authentication import TokenAuthentication
from challenges.views import proxy_challenge_view
from data_security.adapters.django.content import content_protection_enabled
assert len(get_manager()._instances)==2
assert content_protection_enabled()
assert TokenAuthentication not in APIView.authentication_classes
assert TokenAuthentication not in proxy_challenge_view.cls.authentication_classes
print(json.dumps({'formal_startup': True,'legacy_tokens_disabled': True}))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code], cwd=isolation.ROOT,
                                env=env, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'"formal_startup": true', result.stdout)

    def test_reused_key_material_and_unauthorized_environment_fail_readiness(self):
        (self.path.parent / 'audit_key.key').write_bytes(self.material['data_key'])
        with self.assertRaises(ContractViolation):
            assemble(config_path=self.path)
        self.config['environment'] = 'production'
        self.path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            assemble(config_path=self.path)


class BusinessBootstrapTests(TransactionTestCase):
    """Real teaching/legal services through B; capture only final HTTP sends."""

    def setUp(self):
        from ai_providers import bind_manager, get_manager
        from data_security.adapters.django import content

        files = configuration(('deepseek', 'qwen'))
        self.path, _, _, self.material, _ = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        components = assemble(config_path=self.path)
        self.addCleanup(bind_manager, get_manager())
        self.addCleanup(content.bind_content_protection, content._protect)
        bind_manager(components['manager'])
        content.bind_content_protection(components['protect_text'])
        self.sent = []
        self.fail_first_send = False

    def tearDown(self):
        directory = os.environ.get('DS_CAPTURE_DIRECTORY')
        if directory:
            path = Path(directory) / (self._testMethodName + '.json')
            path.write_text(json.dumps({'real_provider_calls': False, 'captures': self.sent},
                                       ensure_ascii=False, indent=2) + '\n')
            path.chmod(0o600)
        super().tearDown()

    def capture_business_send(self, session, prepared, **kwargs):
        from urllib.parse import urlsplit

        parsed = urlsplit(prepared.url)
        endpoint = parsed._replace(query='', fragment='').geturl()
        self.assertIn(endpoint, (
            'https://api.deepseek.com/chat/completions',
            'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        ))
        self.assertFalse(parsed.query)
        body = json.loads(prepared.body)
        self.assertEqual(set(body), {'model', 'messages', 'temperature', 'max_tokens', 'stream'})
        self.assertTrue(all(set(item) == {'role', 'content'} for item in body['messages']))
        serialized = json.dumps(body, ensure_ascii=False)
        # Use boolean assertions so a failed check cannot print a body or credential.
        for forbidden in (
            'a@example.invalid', '192.0.2.1', '4111111111111111',
            'synthetic-never-send-credential', 'synthetic-private-metadata',
            'synthetic-never-send-flag',
        ):
            self.assertFalse(forbidden in serialized, 'final request contains excluded synthetic content')
        self.assertTrue(all(
            value.decode('utf-8') not in serialized
            for name, value in self.material.items() if name in ('deepseek', 'qwen')
        ), 'provider material entered the request body')
        audit_count = SecurityAuditRecord.objects.count()
        self.assertGreater(audit_count, 0)
        # Never retain auth headers, raw credentials, raw responses or query strings.
        self.sent.append({'endpoint': endpoint, 'body': body, 'audit_count': audit_count})
        response = requests.Response()
        response.status_code = 503 if self.fail_first_send and len(self.sent) == 1 else 200
        result = {'choices': [{'message': {'content': (
            'a@example.invalid 192.0.2.1 4111111111111111 safe business answer\n'
            'system prompt: synthetic-internal-instruction'
        )}}], 'usage': {}}
        response._content = json.dumps(result).encode()
        response._content_consumed = True
        return response

    def test_teaching_chat_reaches_real_send_after_context_and_history_projection(self):
        from django.test import override_settings
        from agents.context.teaching_context import SharedTeachingContextBuilder
        from ai_assistant.service import MultiAgentChatService

        teaching = SharedTeachingContextBuilder().build(
            task_type='knowledge_explanation',
            knowledge_context={'definition': 'network explanation a@example.invalid',
                               'metadata': {'private': 'synthetic-private-metadata'}},
            student_profile={'learningGoals': 'learn network isolation',
                             'private': 'synthetic-private-metadata'},
        )
        context = {
            'teaching_context': teaching,
            'challenge_info': {
                'title': 'Synthetic network exercise', 'category_name': 'network',
                'difficulty': 'easy', 'description': 'public 192.0.2.1 description',
                'flag': 'synthetic-never-send-flag', 'private': 'synthetic-private-metadata',
            },
        }
        history = [{'role': 'user', 'content': 'a@example.invalid ' + 'H' * 56,
                    'private': 'synthetic-private-metadata'}]
        with override_settings(TUTOR_PROMPT_BUDGETS={'history_chars': 64}), \
                patch.object(requests.Session, 'send', autospec=True, side_effect=self.capture_business_send):
            result = asyncio.run(MultiAgentChatService().chat_with_agent(
                'analyst',
                'Explain network isolation a@example.invalid 192.0.2.1 4111111111111111 '
                'Bearer synthetic-never-send-credential',
                context, history,
            ))
        self.assertEqual(result['provider'], 'deepseek')
        self.assertEqual(len(self.sent), 1)
        messages = self.sent[0]['body']['messages']
        self.assertTrue(any('network explanation' in item['content'] for item in messages))
        self.assertTrue(any('without revealing flags or backend data' in item['content'] for item in messages))
        self.assertFalse(any('invalid' in item['content'] for item in messages),
                         'history was truncated before protection')
        self.assertTrue('safe business answer' in result['content'])
        self.assertFalse('synthetic-internal-instruction' in result['content'])
        self.assertFalse('a@example.invalid' in result['content'])
        self.assertNotIn('raw_response', result)

    def test_compliance_agent_reaches_real_send_with_minimal_evidence(self):
        from types import SimpleNamespace
        from django.test import override_settings
        from legal.services.compliance_agent import ComplianceAgent

        task = SimpleNamespace(id=1, title='Synthetic compliance task', source_type='text',
                               input_text='Check a@example.invalid 192.0.2.1 4111111111111111')
        assessment = SimpleNamespace(severity='low', score=1, matched_keywords=['test'],
                                     description='Review synthetic scope', recommendation='Check isolation')
        evidence = [{'title': 'Synthetic clause', 'score': 0.8,
                     'text': 'X' * 294 + ' a@example.invalid',
                     'metadata': {'private': 'synthetic-private-metadata'}}]
        with override_settings(LEGAL_COMPLIANCE_AGENT_USE_LLM=True), \
                patch.object(requests.Session, 'send', autospec=True, side_effect=self.capture_business_send):
            result = ComplianceAgent().analyze(task=task, evidence=evidence, assessment=assessment)
        self.assertTrue(result['success'])
        self.assertEqual(result['provider'], 'qwen')
        self.assertEqual(len(self.sent), 1)
        messages = self.sent[0]['body']['messages']
        self.assertTrue(any('必须基于证据回答，不得编造法规条款' in item['content'] for item in messages))
        self.assertTrue(any('Synthetic clause' in item['content'] for item in messages))
        self.assertFalse(any('a@' in item['content'] for item in messages),
                         'evidence was truncated before protection')
        self.assertEqual(set(result['input_payload']), {'task_id', 'evidence_count'})
        self.assertEqual(set(result['output_payload']['evidence'][0]), {'title', 'score', 'text'})
        self.assertTrue('safe business answer' in result['output_payload']['content'])
        self.assertFalse('synthetic-internal-instruction' in result['output_payload']['content'])
        self.assertFalse('a@example.invalid' in result['output_payload']['content'])

    def test_teaching_provider_failure_reprotects_before_cross_provider_send(self):
        from ai_assistant.service import MultiAgentChatService

        self.fail_first_send = True
        with patch.object(requests.Session, 'send', autospec=True, side_effect=self.capture_business_send):
            result = asyncio.run(MultiAgentChatService().chat_with_agent(
                'analyst', 'Explain a@example.invalid 192.0.2.1 4111111111111111',
                {'model_id': 'deepseek'},
            ))
        self.assertEqual(result['provider'], 'qwen')
        self.assertEqual([item['endpoint'] for item in self.sent], [
            'https://api.deepseek.com/chat/completions',
            'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        ])
        self.assertEqual([item['body']['model'] for item in self.sent], ['deepseek-v4-pro', 'qwen-max'])
        self.assertGreater(self.sent[1]['audit_count'], self.sent[0]['audit_count'])
        self.assertTrue('safe business answer' in result['content'])
        self.assertFalse('synthetic-internal-instruction' in result['content'])
        self.assertNotIn('provider_error', result)

    def test_legal_rag_retry_switches_real_provider_without_raw_evidence(self):
        from django.test import override_settings
        from legal_kb.services.rag_answer_service import RagAnswerService
        from legal_kb.services.retrieval_service import LegalRetrievalService

        records = [{'id': 1, 'object_id': 1, 'source_type': 'legal_clause',
                    'title': 'Synthetic legal source', 'score': 0.8,
                    'text': 'X' * 594 + ' a@example.invalid 192.0.2.1 4111111111111111',
                    'metadata': {'audit_event_id': 7, 'private': 'synthetic-private-metadata'}}]
        self.fail_first_send = True
        with override_settings(LEGAL_KB_RAG_USE_LLM=True, LEGAL_KB_RAG_AGENT_ID='compliance_officer'), \
                patch.object(LegalRetrievalService, 'retrieve', return_value=records), \
                patch.object(requests.Session, 'send', autospec=True, side_effect=self.capture_business_send):
            result = RagAnswerService().answer(
                query='Audit a@example.invalid 192.0.2.1 4111111111111111 '
                      'Bearer synthetic-never-send-credential',
                include_raw=True,
            )
        self.assertEqual(result['provider'], 'deepseek')
        self.assertEqual([item['endpoint'] for item in self.sent], [
            'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
            'https://api.deepseek.com/chat/completions',
        ])
        self.assertEqual([item['body']['model'] for item in self.sent], ['qwen-max', 'deepseek-v4-pro'])
        self.assertGreater(self.sent[1]['audit_count'], self.sent[0]['audit_count'])
        for item in self.sent:
            messages = item['body']['messages']
            self.assertTrue(any('不直接给出 flag' in message['content'] for message in messages))
            self.assertTrue(any('Synthetic legal source' in message['content'] for message in messages))
            self.assertFalse(any('a@' in message['content'] for message in messages),
                             'citation was truncated before protection')
        self.assertEqual(result['citations'][0]['metadata'], {'audit_event_id': 7})
        self.assertNotIn('results', result)
        self.assertNotIn('provider_error', result)
        self.assertTrue('safe business answer' in result['answer'])
        self.assertFalse('synthetic-internal-instruction' in result['answer'])
        self.assertFalse('a@example.invalid' in result['answer'])
