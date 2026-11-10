import ast
from dataclasses import replace
import inspect
import ipaddress
import json
from pathlib import Path
import random
import re
import secrets
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from data_security.tests.phase2_fixtures import *
from data_security.core import crypto, redaction
from ctf_backend.security_bootstrap import (bind_legacy_for_tests, validate_production_inputs,
                                            validate_production_random)
from tools.data_security.dependencies import check_source, scan
from tools.data_security.watchdog import session_processes

ROOT = Path(__file__).resolve().parents[3]
BASELINE = '2970a4cb18103b8de4ac7f04a4ea1aa6322b5989'


class RandomSourceTests(unittest.TestCase):
    def test_ten_thousand_os_random_envelopes(self):
        obj, key = examples()[ObjectContext], reference_key()
        salts, nonces, ciphertexts = set(), set(), set()
        validate_production_random(secrets.token_bytes)
        from data_security.application.crypto_service import CryptoService
        service = CryptoService(keys=FakeKeys(), service_identity='service/fixture', random_bytes=secrets.token_bytes,
            environment=Environment.TEST, limits=BASELINE_LIMITS)
        payload = text('synthetic sample')
        for _ in range(10000):
            envelope = service.seal(payload, obj, key)
            self.assertIsInstance(envelope, CipherEnvelope)
            self.assertEqual((len(envelope.kdf_salt), len(envelope.nonce)), (16, 12))
            salts.add(envelope.kdf_salt)
            nonces.add(envelope.nonce)
            ciphertexts.add(envelope.ciphertext_and_tag)
        self.assertEqual((len(salts), len(nonces), len(ciphertexts)), (10000, 10000, 10000))
        self.assertEqual(service.open(envelope, obj, key), payload)

    def test_mechanism_and_formal_input_guards_not_statistical_proof(self):
        self.assertIsInstance(secrets._sysrand, random.SystemRandom)
        self.assertIn('_sysrand.randbytes', inspect.getsource(secrets.token_bytes))
        self.assertIn('_urandom', inspect.getsource(random.SystemRandom.randbytes))
        validate_production_inputs(random_bytes=secrets.token_bytes)
        for source in (lambda n: bytes(n), random.Random(7).randbytes, lambda n: secrets.token_bytes(n)):
            with self.assertRaises(ContractViolation):
                validate_production_random(source)
        snapshot, _ = policy()
        for key, fake in (('policy', MemoryPolicy(snapshot)), ('keys', FakeKeys()), ('audit', MemoryAudit())):
            with self.assertRaises(ContractViolation):
                validate_production_inputs(random_bytes=secrets.token_bytes, **{key: fake})
        with self.assertRaises(ContractViolation):
            bind_legacy_for_tests(environment=Environment.PRODUCTION)


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        from data_security.adapters.tabular import legacy as tabular
        from data_security.adapters.django import legacy as web
        self.old = (tabular._detect, web._confidentiality)
        self.modules = tabular, web
        bind_legacy_for_tests(environment=Environment.TEST)

    def tearDown(self):
        self.modules[0]._detect, self.modules[1]._confidentiality = self.old

    def baseline_nodes(self, path, names):
        source = subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=ROOT)
        nodes = [node for node in ast.parse(source).body if
                 isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names or
                 isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)]
        namespace = {'re': re, 'ipaddress': ipaddress, 'InputError': ValueError,
                     'Tuple': tuple, 'List': list}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<trusted-baseline>', 'exec'), namespace)
        return namespace

    def test_original_candidates_golden_equivalence_with_m0_injection(self):
        from data_security.tests.synthetic import samples
        from mainline1.rules import candidates
        original = self.baseline_nodes('backend/mainline1/rules.py', {'EMAIL', 'IPV4', 'CARD', 'candidates'})['candidates']
        for sample in samples():
            for implementation in ('email_ascii_v1', 'ipv4_v1', 'luhn_candidate_v1'):
                self.assertEqual(tuple(candidates(implementation, sample.text)), tuple(original(implementation, sample.text)))
        for value in ('', '🙂a@example.invalid.', '192.0.2.1/24', 'a..b@example.invalid', '010.0.0.1', 'a192.0.2.1b',
                      'a@example.invalid ' + 'normal ' * 15 + 'b@example.invalid',
                      '192.0.2.1 ' + 'normal ' * 15 + '198.51.100.1'):
            for implementation in ('email_ascii_v1', 'ipv4_v1', 'luhn_candidate_v1'):
                self.assertEqual(tuple(candidates(implementation, value)), tuple(original(implementation, value)))
        calls = []
        def injected(payload, limits):
            calls.append((payload, limits))
            return ()
        self.modules[0].bind_detect(injected)
        self.assertEqual(tuple(candidates('ipv4_v1', '192.0.2.1')), ())
        self.assertEqual(len(calls), 1)
        self.assertIsInstance(calls[0][0], BoundedPayload)

    def test_original_output_compatibility_and_prompt_protection_retained(self):
        from ai_assistant.security import OutputSanitizer
        old = self.baseline_nodes('backend/ai_assistant/security.py', {'OutputSanitizer'})['OutputSanitizer']()
        new = OutputSanitizer()
        values = ('normal teaching text', '10.0.0.2 / 127.0.0.1 / 172.16.0.1 / 192.168.2.1',
                  'system prompt: do not disclose internal instructions',
                  'password=' + root_key().hex(), 'sk-' + root_key().hex()[:48],
                  'connect 10.0.0.1.', 'x10.999.0.1y', '192.168.1.1/24')
        for value in values:
            self.assertEqual(new.sanitize(value), old.sanitize(value))
        for prefix, count in (('AKIA', 16), ('sk-', 48), ('ghp_', 36)):
            value = prefix + root_key().hex().upper()[:count]
            self.assertEqual(new.sanitize(value), old.sanitize(value))

    def test_unbound_output_matches_phase1_including_legacy_edge_semantics(self):
        from ai_assistant.security import OutputSanitizer
        from data_security.tests.synthetic import samples
        self.modules[1]._confidentiality = None
        old = self.baseline_nodes('backend/ai_assistant/security.py', {'OutputSanitizer'})['OutputSanitizer']()
        new = OutputSanitizer()
        marker = root_key().hex()
        values = ['', 'ordinary 🙂 text', 'a' * 65537, 'connect 10.0.0.1.', 'x10.999.0.1y',
            '10.0.0.1 172.16.0.1 192.168.0.1 127.0.0.1 10.0.0.1',
            'password=' + marker[:12] + './' + marker[12:], 'password="' + marker[:12] + ' suffix"',
            'PASSWORD=' + marker, 'sk-' + marker + '-suffix',
            'system prompt: internal instructions', '系统提示词：不能泄露',
            'password=' + marker + ' 10.0.0.1 system prompt: hidden instructions']
        values += [sample.text for sample in samples()]
        for prefix, count in (('AKIA', 16), ('sk-', 48), ('ghp_', 36)):
            for suffix in ('', './suffix', ' suffix'):
                values.append(prefix + marker.upper()[:count] + suffix)
        for kind in ('', 'RSA ', 'EC ', 'DSA ', 'OPENSSH '):
            header = '-----BEGIN ' + kind + 'PRIVATE KEY-----'
            values.extend((header + '\n' + marker,
                header + '\n' + marker + '\n-----END ' + kind + 'PRIVATE KEY-----'))
        for index, value in enumerate(values):
            with self.subTest(sample=index):
                self.assertEqual(new.sanitize(value), old.sanitize(value))

    def test_unbound_legal_matches_phase1_truncation_and_substitutions(self):
        from legal.services import fact_redactor
        self.modules[1]._confidentiality = None
        old = self.baseline_nodes('backend/legal/services/fact_redactor.py',
            {'TOKEN_PATTERN', 'FLAG_PATTERN', 'redact_manual_notes'})
        marker = root_key().hex()
        values = (None, '', ' ordinary 🙂 text ', 'password=' + marker,
            'Authorization: Bearer ' + marker, 'cookie=part=' + marker + '; extra=' + marker,
            'password="' + marker[:12] + ' ' + marker[12:] + '"',
            'TOKEN=' + marker + ', password=' + marker + '; flag{' + marker + '}',
            'flag{' + marker + '}', 'flag{' + 'x' * 501 + '}', 'a' * 65537 + ' token=' + marker)
        for limit in (None, -1, 0, 1, 8, 9, 12, 40, 4000, 70000):
            settings = SimpleNamespace(**({} if limit is None else {'LEGAL_FACT_MAX_MANUAL_CHARS': limit}))
            old['settings'] = settings
            with patch.object(fact_redactor, 'settings', settings):
                for index, value in enumerate(values):
                    with self.subTest(limit=limit, sample=index):
                        self.assertEqual(fact_redactor.redact_manual_notes(value), old['redact_manual_notes'](value))

    def test_explicit_binding_switches_existing_entrypoints_and_keeps_empty_result(self):
        from ai_assistant.security import OutputSanitizer
        from legal.services import fact_redactor
        self.modules[1]._confidentiality = None
        sanitizer = OutputSanitizer()
        self.assertEqual(sanitizer.sanitize('original'), ('original', []))
        calls = []
        def injected(value, profile):
            calls.append((value, profile))
            return '', ()
        self.modules[1].bind_confidentiality(injected)
        self.assertEqual(sanitizer.sanitize('original'), ('', []))
        with patch.object(fact_redactor, 'settings', SimpleNamespace(LEGAL_FACT_MAX_MANUAL_CHARS=2)):
            self.assertEqual(fact_redactor.redact_manual_notes('original'), '')
        self.assertEqual(calls, [('original', 'output-v1'), ('original', 'legal-v1')])
        bind_legacy_for_tests(environment=Environment.TEST)
        delegate = self.modules[1]._confidentiality
        self.assertIs(delegate.keywords['secret_patterns'], self.modules[1].LEGACY_SECRET)
        self.assertIs(delegate.keywords['token_pattern'], self.modules[1].LEGACY_TOKEN)
        self.assertIs(delegate.keywords['internal_patterns'], self.modules[1].LEGACY_INTERNAL)

    def test_complete_private_block_and_legal_pretruncate_no_fragment(self):
        from ai_assistant.security import OutputSanitizer
        from legal.services import fact_redactor
        header = '-----BEGIN RSA PRIVATE KEY-----'
        footer = '-----END RSA PRIVATE KEY-----'
        body = root_key().hex()
        for value in (header + '\n' + body + '\n' + footer, header + '\n' + body):
            result, warnings = OutputSanitizer().sanitize(value)
            self.assertNotIn(body, result)
            self.assertNotIn(body[-8:], result)
            self.assertTrue(warnings)
        with patch.object(fact_redactor, 'settings', SimpleNamespace(LEGAL_FACT_MAX_MANUAL_CHARS=12)):
            result = fact_redactor.redact_manual_notes('password=' + body)
            self.assertNotIn(body[:3], result)
            self.assertEqual(result, 'password=[RE')
        with patch.object(fact_redactor, 'settings', SimpleNamespace(LEGAL_FACT_MAX_MANUAL_CHARS=4000)):
            result = fact_redactor.redact_manual_notes('password=' + body + ' flag{' + body + '}')
            self.assertNotIn(body, result)
            self.assertIn('flag{[REDACTED]}', result)

    def test_unbound_detector_and_faulting_bound_delegate_fail_closed(self):
        from mainline1.rules import candidates
        from mainline1.parsing import InputError
        from ai_assistant.security import OutputSanitizer
        from legal.services import fact_redactor
        self.modules[0]._detect = None
        self.modules[1]._confidentiality = None
        with self.assertRaises(InputError):
            tuple(candidates('email_ascii_v1', 'a@example.invalid'))
        def broken(*args):
            raise RuntimeError(root_key().hex())
        for delegate in (lambda *args: None, lambda *args: ('x', []), broken):
            self.modules[1].bind_confidentiality(delegate)
            self.assertEqual(OutputSanitizer().sanitize('original'),
                ('[内容暂不可用]', ['内容保护未就绪，已阻断输出']))
            with patch.object(fact_redactor, 'settings', SimpleNamespace()):
                self.assertEqual(fact_redactor.redact_manual_notes('original'), '[内容暂不可用]')
        for detector in (lambda *args: None, lambda *args: (None,)):
            self.modules[0].bind_detect(detector)
            with self.assertRaises(InputError):
                tuple(candidates('email_ascii_v1', 'a@example.invalid'))
        self.modules[0].bind_detect(broken)
        with self.assertRaises(InputError):
            tuple(candidates('email_ascii_v1', 'a@example.invalid'))


class PhaseBoundaryTests(unittest.TestCase):
    def test_authorized_stage_declaration_keeps_matrix_and_future_modules_closed(self):
        count, violations = scan(ROOT, phase=7)
        self.assertGreater(count, 440)
        self.assertFalse(violations)
        self.assertTrue(scan(ROOT, phase=1)[1])
        self.assertTrue(check_source('backend/data_security/adapters/tabular/legacy.py',
                                     'from data_security.core.redaction import detect', phase=2))
        self.assertTrue(check_source('backend/data_security/application/protection.py',
                                     'from data_security.adapters.keys import Resolver', phase=2))
        self.assertTrue(check_source('backend/users/views.py',
                                     'from data_security.contracts import Finding', phase=2))
        for filename in ('backend/mainline1/rules.py', 'backend/ai_assistant/security.py', 'backend/legal/services/fact_redactor.py'):
            source = (ROOT / filename).read_text()
            self.assertNotIn('TOKEN_PATTERN', source)
            self.assertNotIn('SECRET_PATTERNS', source)
            self.assertNotIn('import ipaddress', source)

    def test_initial_sdk_pid_is_pinned_and_resume_still_requires_same_id(self):
        item = {'pid': 99, 'start_ticks': 123, 'cwd': str(ROOT), 'argv': ['/bin/claude', '-p']}
        config = {'workdir': str(ROOT), 'session_id': 'fixture-id', 'initial_process': item}
        with patch('tools.data_security.watchdog.Path.iterdir', return_value=[Path('/proc/99')]), \
             patch('tools.data_security.watchdog.process', return_value=item):
            self.assertEqual(session_processes(config), [item])
            self.assertFalse(session_processes({**config, 'initial_process': {**item, 'start_ticks': 122}}))
        resumed = {**item, 'argv': ['/bin/claude', '--resume', 'wrong-id']}
        with patch('tools.data_security.watchdog.Path.iterdir', return_value=[Path('/proc/99')]), \
             patch('tools.data_security.watchdog.process', return_value=resumed):
            self.assertFalse(session_processes({**config, 'initial_process': resumed}))
