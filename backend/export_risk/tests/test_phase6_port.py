"""Request-scoped M6 risk port against the original PostgreSQL risk/quota services."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from unittest.mock import Mock, patch

from django.db import DatabaseError, connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from data_security.adapters.persistence import risk
from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import ContractViolation, ExecutionBinding, ProtectionError, ReasonCode
from data_security.tests.fixtures import examples
from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaService
from export_risk.contracts import AuthorizationResult, ExecutionAuthorization, RecommendedAction, SourceMode
from export_risk.decisions import service
from export_risk.models import EventOutbox, ExecutionAuthorizationRecord, RiskDecision
from export_risk.tests.test_decisions import make_assessment, make_auth_snapshot, make_request


class RiskPortFixture:
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        self.binding = replace(examples()[ExecutionBinding], expires_at=timezone.now() + timedelta(minutes=5))
        self.request = replace(make_request(fp=self.binding.request_fingerprint),
            request_id=self.binding.request_id, subject_id=self.binding.subject_ref,
            asset_version=self.binding.asset_version)
        self.assess = Mock(return_value=replace(make_assessment(RecommendedAction.ALLOW),
            request_id=self.request.request_id, request_fingerprint=self.request.request_fingerprint,
            policy_version=self.binding.policy_binding.risk_version))
        self.authorize = Mock(return_value=replace(make_auth_snapshot(),
            subject_id=self.request.subject_id, data_domain=self.binding.domain_ref))
        self.quota = DjangoQuotaPort(environment='test', window_key='risk-port', limit=10, ttl_seconds=60)
        self.port = self.adapter()
        decision_id = self.port.decide(self.request, self.binding.policy_binding)
        self.assertIsInstance(decision_id, str)
        self.binding = replace(self.binding, decision_id=decision_id)
        self.quota.reserve(self.binding)
        # The fixture's decide now checks permission before any hold. The tests
        # below count only their own issue/recheck/consume boundary calls.
        self.authorize.reset_mock()

    def adapter(self, **changes):
        values = dict(request=self.request, scope=self.binding.scope, domain_ref=self.binding.domain_ref,
            policy_binding=self.binding.policy_binding, environment='test', assess=self.assess,
            authorize=self.authorize, active_until=self.quota.active_until)
        values.update(changes)
        return risk.DjangoRiskPort(**values)


class RiskPortTests(RiskPortFixture, TestCase):
    def test_decide_replays_owner_reference_and_not_orm_or_duplicate_model(self):
        self.assertEqual(self.port.decide(self.request, self.binding.policy_binding), self.binding.decision_id)
        rebuilt = self.adapter()
        self.assertEqual(rebuilt.decide(self.request, self.binding.policy_binding), self.binding.decision_id)
        self.assertEqual(RiskDecision.objects.count(), 1)
        self.assess.assert_called_with(self.request, self.binding.policy_binding)

    def test_issue_claims_once_and_recheck_returns_original_dto_without_quota_writes(self):
        with patch.object(QuotaService, 'reserve', side_effect=AssertionError('second reserve')), \
                patch.object(QuotaService, 'commit', side_effect=AssertionError('risk commit')), \
                patch.object(QuotaService, 'release', side_effect=AssertionError('risk release')):
            issued = self.port.issue(self.binding)
            self.assertIsInstance(issued, ExecutionAuthorization)
            self.assertEqual(issued.valid_until, QuotaReservation.objects.get().expires_at.isoformat())
            self.assertEqual(self.port.recheck(self.binding), issued)
            self.assertIsInstance(self.port.issue(self.binding), ProtectionError)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_reconstructed_adapter_rechecks_claimed_execution_without_reclaim(self):
        issued = self.port.issue(self.binding)
        rebuilt = self.adapter()
        self.assertIsInstance(rebuilt.recheck(self.binding), ProtectionError)
        self.assertEqual(rebuilt.decide(self.request, self.binding.policy_binding), issued.decision_id)
        with patch.object(risk, 'claim', side_effect=AssertionError('reclaimed')):
            self.assertEqual(rebuilt.recheck(self.binding), issued)

    def test_all_execution_fields_are_bound_before_authorization_lookup(self):
        changes = ({'request_id': 'other/request'}, {'request_fingerprint': '1' * 64},
            {'asset_version': 'other/asset'}, {'subject_ref': 'other/subject'}, {'quantity': 9},
            {'environment': 'evaluation'}, {'domain_ref': 'other/domain'},
            {'decision_id': 'other/decision'}, {'policy_binding': replace(self.binding.policy_binding, risk_hash='2' * 64)},
            {'scope': replace(self.binding.scope, sheets=(replace(self.binding.scope.sheets[0], row_ranges=((1, 1),)),))})
        for change in changes:
            with self.subTest(field=next(iter(change))):
                self.assertIsInstance(self.port.issue(replace(self.binding, **change)), ProtectionError)
        self.authorize.assert_not_called()
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())

    def test_quota_binding_binds_authorization_execution_reservation_expiry_and_key(self):
        for field, value in (('authorization_id', 'other/auth'), ('execution_id', 'other/execution'),
                             ('reservation_id', 'other/reservation'), ('idempotency_key', 'other/key'),
                             ('expires_at', self.binding.expires_at + timedelta(seconds=1))):
            with self.subTest(field=field):
                self.assertIsInstance(self.port.issue(replace(self.binding, **{field: value})), ProtectionError)
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_current_authorization_is_fetched_for_each_recheck(self):
        self.port.issue(self.binding)
        initial = self.authorize.return_value
        for change in ({'result': AuthorizationResult.FORBIDDEN}, {'allowed_scope': ()},
                       {'allowed_operations': ()}, {'allowed_recipients': ()}, {'data_domain': 'other/domain'},
                       {'environment': 'evaluation'}, {'source_mode': SourceMode.PRODUCTION},
                       {'valid_until': (timezone.now() - timedelta(seconds=1)).isoformat()}):
            self.authorize.return_value = replace(initial, **change)
            with self.subTest(field=next(iter(change))):
                self.assertIsInstance(self.port.recheck(self.binding), ProtectionError)
        self.assertEqual(self.authorize.call_count, 9)
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_shorter_current_grant_is_not_extended_on_later_recheck(self):
        self.port.issue(self.binding)
        initial = self.authorize.return_value
        until = timezone.now() + timedelta(seconds=10)
        self.authorize.return_value = replace(initial, valid_until=until.isoformat())
        self.assertEqual(self.port.recheck(self.binding).valid_until, until.isoformat())
        self.authorize.return_value = initial
        self.assertEqual(self.port.recheck(self.binding).valid_until, until.isoformat())

    def test_failed_claim_rolls_back_authorization_and_outbox_not_hold(self):
        with patch.object(risk, 'claim', return_value=False):
            self.assertIsInstance(self.port.issue(self.binding), ProtectionError)
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertFalse(EventOutbox.objects.filter(event_type='execution.authorized').exists())
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)
        self.assertIsInstance(self.port.issue(self.binding), ExecutionAuthorization)

    def test_database_failure_is_unknown_and_does_not_release(self):
        with patch.object(risk, 'claim', side_effect=DatabaseError('synthetic fault')):
            self.assertEqual(self.port.issue(self.binding).code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_downstream_uow_failure_rolls_back_claim(self):
        with self.assertRaisesRegex(RuntimeError, 'audit failed'):
            with DjangoUnitOfWork() as work:
                self.assertIsInstance(self.port.issue(self.binding), ExecutionAuthorization)
                work.commit()
                raise RuntimeError('audit failed')
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_unknown_quota_or_invalidated_decision_never_reopens_execution(self):
        self.port.issue(self.binding)
        self.quota.reconcile(self.binding, None, 'proof/unknown')
        self.assertIsInstance(self.port.recheck(self.binding), ProtectionError)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 10)
        service.invalidate_decision(self.binding.decision_id)
        self.assertIsInstance(self.port.recheck(self.binding), ProtectionError)
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 10)

    def test_decide_rejects_changed_request_policy_and_unbound_assessment(self):
        self.assertIsInstance(self.port.decide(replace(self.request, recipient_id='other/recipient'),
                                             self.binding.policy_binding), ProtectionError)
        self.assertIsInstance(self.port.issue(self.binding), ProtectionError)
        self.assertIsInstance(self.port.decide(self.request, replace(self.binding.policy_binding, risk_hash='2' * 64)),
                              ProtectionError)
        original = self.assess.return_value
        for change in ({'request_id': 'other/request'}, {'request_fingerprint': '1' * 64},
                       {'policy_version': 'other/policy'}, {'input_source_mode': SourceMode.PRODUCTION}):
            self.assess.return_value = replace(original, **change)
            self.assertIsInstance(self.port.decide(self.request, self.binding.policy_binding), ProtectionError)
        self.assertEqual(RiskDecision.objects.count(), 1)

    def test_production_configuration_is_not_implicitly_authorized(self):
        for changes in ({'environment': 'production'}, {'request': replace(self.request, source_mode=SourceMode.PRODUCTION)},
                        {'request': replace(self.request, environment='evaluation')}):
            with self.assertRaises(ContractViolation):
                self.adapter(**changes)


class RiskConsumeTests(RiskPortFixture, TransactionTestCase):
    def test_consume_requires_outer_uow_and_rechecks_current_authorization(self):
        self.port.issue(self.binding)
        self.assertFalse(connection.in_atomic_block)
        self.assertEqual(self.port.consume(self.binding).code, ReasonCode.AUTHORIZATION_DENIED)
        self.authorize.return_value = replace(self.authorize.return_value, result=AuthorizationResult.FORBIDDEN)
        with DjangoUnitOfWork():
            self.assertIsInstance(self.port.consume(self.binding), ProtectionError)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_consume_rolls_back_with_uow_and_never_writes_quota_or_reclaims(self):
        self.port.issue(self.binding)
        with patch.object(risk, 'claim', side_effect=AssertionError('reclaimed')), \
                patch.object(QuotaService, 'commit', side_effect=AssertionError('risk settlement')), \
                patch.object(QuotaService, 'release', side_effect=AssertionError('risk release')):
            with DjangoUnitOfWork():
                self.assertIsInstance(self.port.consume(self.binding), ExecutionAuthorization)
                self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
            self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
            with DjangoUnitOfWork() as work:
                self.assertIsInstance(self.port.consume(self.binding), ExecutionAuthorization)
                work.commit()
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'consumed')
        with DjangoUnitOfWork():
            self.assertIsInstance(self.port.consume(self.binding), ProtectionError)
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)
        self.assertEqual(QuotaReservation.objects.count(), 1)

    def test_consume_database_failure_does_not_mark_consumed_or_release(self):
        self.port.issue(self.binding)
        with DjangoUnitOfWork():
            with patch.object(risk, 'consume', side_effect=DatabaseError('injected')):
                self.assertEqual(self.port.consume(self.binding).code, ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_consume_unknown_hold_never_reopens(self):
        self.port.issue(self.binding)
        self.quota.reconcile(self.binding, None, 'proof/unknown')
        with DjangoUnitOfWork():
            self.assertIsInstance(self.port.consume(self.binding), ProtectionError)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')
        self.assertEqual(QuotaBucket.objects.get().unknown_reserved, 10)


class RiskPortConcurrencyTests(RiskPortFixture, TransactionTestCase):
    def test_competing_issue_claims_exactly_once(self):
        barrier = Barrier(2)

        def issue():
            try:
                barrier.wait(timeout=10)
                return self.port.issue(self.binding)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [f.result(timeout=15) for f in [pool.submit(issue), pool.submit(issue)]]
        self.assertEqual(sum(isinstance(value, ExecutionAuthorization) for value in results), 1)
        self.assertEqual(sum(isinstance(value, ProtectionError) for value in results), 1)
        self.assertEqual(ExecutionAuthorizationRecord.objects.count(), 1)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)
