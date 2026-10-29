"""HTTP fixtures exercise the contract, NOT a real Juice Shop deployment."""

import json
import socket
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from threading import Thread
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from learning_analytics.models import LearningEvent
from learning_map.models import VerificationFact
from skill_review.models import DownstreamNotice, RetestAssignment, VerificationResult
from teaching_agent.models import ModelCallRecord
from . import tests as fixtures
from .models import EnvironmentApproval, RepairClaim, ServerEvidence
from .policy import environment_binding
from .verifiers import VerifierUnavailable, observe_challenge


@contextmanager
def fixture_server():
    state = {'solved': False, 'status': 200, 'body': None, 'requests': 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state['requests'] += 1
            self.send_response(state['status'] if self.path == '/api/Challenges' else 404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            body = state['body']
            if body is None:
                body = json.dumps({'data': [{'key': 'directoryListingChallenge', 'solved': state['solved']}]}).encode()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class HTTPVerifierTests(SimpleTestCase):
    def test_actual_http_parser_and_status_transition(self):
        with fixture_server() as (port, state):
            endpoint = f'http://127.0.0.1:{port}'
            self.assertFalse(observe_challenge(endpoint, 'directoryListingChallenge')['solved'])
            state['solved'] = True
            self.assertTrue(observe_challenge(endpoint, 'directoryListingChallenge')['solved'])

    def test_redirect_and_missing_or_forged_schema_are_fail_closed(self):
        with fixture_server() as (port, state):
            for status, body in ((302, b'{}'), (503, b'{}'), (200, b'bad json'),
                                 (200, b'{"data":[]}'),
                                 (200, b'{"data":[{"key":"directoryListingChallenge","solved":"true"}]}'),
                                 (200, b'x' * (1024 * 1024 + 1))):
                state.update(status=status, body=body)
                with self.assertRaises(VerifierUnavailable):
                    observe_challenge(f'http://127.0.0.1:{port}', 'directoryListingChallenge')

    def test_real_release_key_is_required_not_the_old_fixture_alias(self):
        with fixture_server() as (port, state):
            endpoint = f'http://127.0.0.1:{port}'
            self.assertFalse(observe_challenge(endpoint, 'directoryListingChallenge')['solved'])
            with self.assertRaises(VerifierUnavailable):
                observe_challenge(endpoint, 'confidentialDocumentChallenge')

    def test_timeout_is_a_verifier_fault(self):
        import requests
        with patch('practical_training.verifiers.requests.Session.get', side_effect=requests.Timeout):
            with self.assertRaises(VerifierUnavailable):
                observe_challenge('http://127.0.0.1:18080', 'directoryListingChallenge')


@override_settings(
    LEARNING_MAP_AI_ENABLED=False, KNOWLEDGE_RAG_SEMANTIC_ENABLED=False,
    AGENT_RUNTIME_SEMANTIC_RETRIEVAL=False, TUTOR_AGENT_ROUTER_ENABLED=False,
    TUTOR_SPECIALISTS_ENABLED=False, TUTOR_CONTEXT_ENABLED=False,
)
class AcceptanceTests(fixtures.TrainingTestCase):
    start = fixtures.EvidenceTests.start
    verify = fixtures.EvidenceTests.verify
    submit_repair = fixtures.RepairTests.submit_repair
    check_repair = fixtures.RepairTests.check_repair

    def test_all_models_disabled_full_http_contract_flow_and_zero_external_calls(self):
        with fixture_server() as (port, state), self.settings(JUICE_SHOP_PORT_MIN=port, JUICE_SHOP_PORT_MAX=port):
            self.container.port = port
            self.container.save()
            approval = EnvironmentApproval.objects.get(container=self.container)
            approval.checks['binding'] = environment_binding(self.container)
            approval.save()
            real_connect = socket.socket.connect
            connections = []

            def local_only(sock, address):
                if address != ('127.0.0.1', port):
                    raise AssertionError(f'Unexpected external connection: {address!r}')
                connections.append(address)
                return real_connect(sock, address)

            with patch('socket.socket.connect', new=local_only), patch(
                'ai_assistant.service.get_ai_assistant_service', side_effect=AssertionError('model called'),
            ) as model_boundary:
                assignment = self.allocate()
                started = self.client.post(self.url(assignment, 'start/'), {}, format='json')
                self.assertEqual(started.status_code, 200, started.content)
                hint = self.client.post(self.url(assignment, 'hints/'), {'level': 1}, format='json')
                self.assertEqual(self.client.post(self.url(assignment, f"hints/{hint.data['record_id']}/display/"), {}, format='json').status_code, 200)
                state['solved'] = True  # Fixture-side signal, not student self-report.
                verified = self.client.post(self.url(assignment, 'verify/'), {'key': 'no-ai-evidence'}, format='json')
                self.assertEqual(verified.status_code, 201, verified.content)
                original = VerificationResult.objects.get(result_id=verified.data['result_id'])
                self.assertEqual(original.independence, 'assisted')
                self.assertTrue(original.module1_fact_ids)
                claim = self.submit_repair(assignment)
                self.assertFalse(claim.data['completed'])
                checked = self.check_repair(assignment, claim.data['claim_id'])
                self.assertEqual(checked.status_code, 201, checked.content)
                self.assertTrue(RepairClaim.objects.get().completed)
                retest = RetestAssignment.objects.get(original_submission=original.submission)
                self.assertEqual(retest.outcome, 'passed')
                self.assertTrue(VerificationFact.objects.filter(retest_of_attempt_id=assignment.attempt.attempt_id).exists())
                review = self.client.put(self.url(assignment, 'review/'), {
                    'original_task_summary': 'Synthetic document exposure', 'error_evidence': verified.data['evidence_id'],
                    'judgment_at_time': 'Public link is not authorization', 'correct_basis': 'Server-side authorization',
                    'next_verification': 'Fresh resource scenario', 'student_reflection': 'Test permitted and denied access',
                }, format='json')
                self.assertEqual(review.status_code, 200, review.content)
                model_boundary.assert_not_called()
            self.assertEqual(state['requests'], 2)
            self.assertEqual(len(connections), 2)
            self.assertEqual(ModelCallRecord.objects.count(), 0)
            self.assertEqual(ServerEvidence.objects.count(), 2)
            self.assertTrue(all(len(event_id) <= 64 for event_id in LearningEvent.objects.values_list('event_id', flat=True)))

    def test_delivery_failure_retries_without_reexecution_or_new_facts(self):
        assignment = self.allocate()
        self.start(assignment)
        with patch('practical_training.delivery.ingest_verification_fact', side_effect=RuntimeError('downstream unavailable')):
            response = self.verify(assignment)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(DownstreamNotice.objects.get().status, 'failed')
        with patch('practical_training.verifiers.observe_challenge', side_effect=AssertionError('must not rerun')):
            call_command('retry_practical_delivery', stdout=StringIO())
            call_command('retry_practical_delivery', stdout=StringIO())
        self.assertEqual(DownstreamNotice.objects.get().status, 'sent')
        self.assertEqual(VerificationFact.objects.count(), 1)
        self.assertTrue(VerificationResult.objects.get().module1_fact_ids)

    def test_unknown_help_is_not_counted_as_independent_retest(self):
        from skill_review.services.submissions import record_analysis_view
        assignment = self.allocate()
        self.start(assignment)
        self.verify(assignment)
        claim = self.submit_repair(assignment)
        record_analysis_view(student=self.student, task=self.repair_task)
        checked = self.check_repair(assignment, claim.data['claim_id'])
        self.assertEqual(checked.status_code, 201)
        self.assertEqual(RepairClaim.objects.get().retest.outcome, 'unknown')

    def test_failed_event_storage_rolls_back_evidence_and_result(self):
        assignment = self.allocate()
        self.start(assignment)
        with patch('practical_training.handoff.emit_event', side_effect=RuntimeError('storage unavailable')):
            with self.assertRaises(RuntimeError):
                self.verify(assignment)
        self.assertFalse(ServerEvidence.objects.exists())
        self.assertFalse(VerificationResult.objects.exists())
