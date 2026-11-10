"""Pre-reservation admission through the original risk-domain eligibility rules."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from queue import Queue
from threading import Event
import time
from unittest.mock import Mock, patch

from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from data_security.adapters.persistence import risk
from data_security.contracts import ExecutionBinding, ProtectionError, ReasonCode
from data_security.tests.fixtures import examples
from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaService
from export_risk.contracts import AuthorizationResult, Obligation, RecommendedAction
from export_risk.models import ExecutionAuthorizationRecord, RiskDecision
from export_risk.tests.test_decisions import make_assessment, make_auth_snapshot, make_request


class PreReservationAdmissionTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.binding = examples()[ExecutionBinding]
        self.request = make_request()
        self.assess = Mock(return_value=make_assessment(RecommendedAction.ALLOW,
                                                       policy=self.binding.policy_binding.risk_version))
        self.authorize = Mock(return_value=make_auth_snapshot())
        self.hold = Mock(side_effect=AssertionError('preflight must not need a hold'))
        self.approval = Mock(status=Mock(return_value='none'))
        self.port = risk.DjangoRiskPort(request=self.request, scope=self.binding.scope,
            domain_ref='d1', policy_binding=self.binding.policy_binding, environment='test',
            assess=self.assess, authorize=self.authorize, active_until=self.hold, approval=self.approval)

    def decide(self):
        return self.port.decide(self.request, self.binding.policy_binding)

    def assert_no_hold_or_grant(self):
        self.hold.assert_not_called()
        self.assertEqual(QuotaBucket.objects.count(), 0)
        self.assertEqual(QuotaReservation.objects.count(), 0)
        self.assertEqual(ExecutionAuthorizationRecord.objects.count(), 0)

    def test_allow_returns_reference_without_reserve_prepare_claim_or_hold_lookup(self):
        with patch.object(QuotaService, 'reserve', side_effect=AssertionError('reserve')), \
                patch.object(risk, 'prepare_execution', side_effect=AssertionError('prepare')), \
                patch.object(risk, 'claim', side_effect=AssertionError('claim')):
            first = self.decide()
            self.assertIsInstance(first, str)
            self.assertEqual(self.decide(), first)
        self.assertEqual(self.authorize.call_count, 2)
        self.assertEqual(RiskDecision.objects.count(), 1)
        self.assert_no_hold_or_grant()

    def test_deny_defer_unapproved_and_unsupported_obligation_never_return_admission(self):
        original = self.assess.return_value
        changes = ({'recommended_action': RecommendedAction.DENY},
                   {'recommended_action': RecommendedAction.DEFER},
                   {'recommended_action': RecommendedAction.REQUIRE_APPROVAL},
                   {'obligations': (Obligation(obligation_id='fixture/unsupported', type='unsupported'),)})
        for change in changes:
            with self.subTest(field=next(iter(change))), transaction.atomic():
                self.assess.return_value = replace(original, **change)
                self.assertEqual(self.decide().code, ReasonCode.AUTHORIZATION_DENIED)
                self.assertIsNone(self.port._decision_id)
                self.assert_no_hold_or_grant()
                transaction.set_rollback(True)

    def test_current_authorization_allowlists_subject_domain_environment_and_expiry_are_required(self):
        original = self.authorize.return_value
        changes = ({'result': AuthorizationResult.FORBIDDEN}, {'allowed_scope': ()},
                   {'allowed_operations': ()}, {'allowed_recipients': ()}, {'subject_id': 'other'},
                   {'data_domain': 'other'}, {'environment': 'evaluation'},
                   {'valid_until': (timezone.now() - timedelta(seconds=1)).isoformat()})
        for change in changes:
            with self.subTest(field=next(iter(change))):
                self.authorize.return_value = replace(original, **change)
                self.assertEqual(self.decide().code, ReasonCode.AUTHORIZATION_DENIED)
                self.assertIsNone(self.port._decision_id)
                self.assert_no_hold_or_grant()

    def test_approval_is_rechecked_and_never_created_by_preflight(self):
        self.assess.return_value = replace(self.assess.return_value,
                                          recommended_action=RecommendedAction.REQUIRE_APPROVAL)
        self.assertIsInstance(self.decide(), ProtectionError)
        decision = RiskDecision.objects.get()
        self.approval.status.assert_called_with(decision.decision_id, self.request.request_fingerprint)
        self.approval.status.return_value = 'approved'
        self.assertEqual(self.decide(), decision.decision_id)
        self.approval.status.return_value = 'revoked'
        self.assertIsInstance(self.decide(), ProtectionError)
        self.assertIsNone(self.port._decision_id)
        self.assert_no_hold_or_grant()

    def test_invalidated_or_expired_decision_and_database_failure_do_not_admit(self):
        decision = self.decide()
        for update in ({'status': 'invalidated'}, {'valid_until': timezone.now() - timedelta(seconds=1)}):
            with transaction.atomic():
                RiskDecision.objects.filter(decision_id=decision).update(**update)
                self.assertEqual(self.decide().code, ReasonCode.AUTHORIZATION_DENIED)
                self.assertIsNone(self.port._decision_id)
                transaction.set_rollback(True)
        with patch.object(risk, 'check_execution_eligibility', side_effect=DatabaseError('omitted')):
            self.assertEqual(self.decide().code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertIsNone(self.port._decision_id)
        self.assert_no_hold_or_grant()

    def test_postgres_decision_lock_wait_rechecks_expiry_before_any_reservation(self):
        decision = self.decide()
        until = timezone.now() + timedelta(seconds=1)
        self.authorize.return_value = replace(self.authorize.return_value, valid_until=until.isoformat())
        pids = Queue()
        def worker():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    pids.put(cursor.fetchone()[0])
                return self.decide()
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                RiskDecision.objects.select_for_update().get(decision_id=decision)
                future = pool.submit(worker)
                pid = pids.get(timeout=5)
                deadline = time.monotonic() + 10
                blocked = False
                while time.monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT cardinality(pg_blocking_pids(%s)) > 0', [pid])
                        blocked = cursor.fetchone()[0]
                    if blocked:
                        break
                    Event().wait(0.01)
                self.assertTrue(blocked, 'real PostgreSQL lock wait was not observed')
                while timezone.now() < until:
                    Event().wait(0.02)
            result = future.result(timeout=15)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertIsNone(self.port._decision_id)
        self.assert_no_hold_or_grant()
