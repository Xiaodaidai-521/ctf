"""The risk service consumes the M6 quota authority's actual, bound deadline."""
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.utils import timezone

from data_security.adapters.persistence.quota import DjangoQuotaPort
from data_security.contracts import ExecutionBinding, ProtectionError
from data_security.tests.fixtures import examples
from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaService
from export_risk.contracts import RecommendedAction
from export_risk.decisions import service
from export_risk.models import ExecutionAuthorizationRecord
from export_risk.tests.test_decisions import make_assessment, make_auth_snapshot, make_request


class RiskQuotaBridgeTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        base = examples()[ExecutionBinding]
        self.request = replace(make_request(fp=base.request_fingerprint), request_id=base.request_id,
            subject_id=base.subject_ref, asset_version=base.asset_version)
        assessment = replace(make_assessment(RecommendedAction.ALLOW), request_id=base.request_id,
            request_fingerprint=base.request_fingerprint)
        decision = service.create_risk_decision(assessment, self.request, idempotency_key='bridge/decision')
        self.binding = replace(base, decision_id=decision.decision_id,
                               expires_at=timezone.now() + timedelta(minutes=5))
        self.snapshot = replace(make_auth_snapshot(), subject_id=base.subject_ref, data_domain=base.domain_ref)
        self.port = DjangoQuotaPort(environment='test', window_key='bridge', limit=10, ttl_seconds=30)
        self.port.reserve(self.binding)

    def require_active(self, *, reservation_id, request_fingerprint, amount=None):
        self.assertEqual(reservation_id, self.binding.reservation_id)
        self.assertEqual(request_fingerprint, self.binding.request_fingerprint)
        if amount is not None:
            self.assertEqual(amount, self.binding.quantity)
        result = self.port.active_until(self.binding)
        return None if isinstance(result, ProtectionError) else result

    def prepare(self):
        return service.prepare_execution(self.binding.decision_id, self.request, self.snapshot,
            idempotency_key='bridge/prepare', environment='test', reservation_id=self.binding.reservation_id,
            authorization_id=self.binding.authorization_id, execution_id=self.binding.execution_id,
            require_active=self.require_active)

    def recheck(self):
        return service.recheck_execution(self.binding.authorization_id, self.request, self.snapshot,
            decision_id=self.binding.decision_id, execution_id=self.binding.execution_id,
            reservation_id=self.binding.reservation_id, environment='test', require_active=self.require_active)

    def test_issue_claim_and_recheck_keep_actual_short_hold_without_second_reserve(self):
        expiry = QuotaReservation.objects.get().expires_at
        self.assertLess(expiry, self.binding.expires_at)
        with patch.object(QuotaService, 'reserve', side_effect=AssertionError('second reserve')), \
                patch.object(QuotaService, 'release', side_effect=AssertionError('risk release')), \
                patch.object(QuotaService, 'commit', side_effect=AssertionError('risk commit')):
            issued = self.prepare()
            self.assertEqual(issued.valid_until, expiry.isoformat())
            self.assertEqual(self.prepare(), issued)
            self.assertTrue(service.claim(issued.authorization_id, require_active=self.require_active))
            self.assertEqual(self.recheck(), issued)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'claiming')

    def test_unknown_hold_denies_recheck_without_releasing_capacity(self):
        issued = self.prepare()
        self.assertTrue(service.claim(issued.authorization_id, require_active=self.require_active))
        self.port.reconcile(self.binding, None, 'proof/unknown')
        self.assertEqual(self.recheck().kind, 'not_executable')
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (0, 10, 0))

    def test_full_binding_mismatch_denies_even_when_legacy_ids_match(self):
        self.binding = replace(self.binding, scope=replace(self.binding.scope,
            sheets=(replace(self.binding.scope.sheets[0], row_ranges=((1, 1),)),)))
        self.assertEqual(self.prepare().kind, 'not_executable')
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_expired_hold_cannot_be_issued_using_longer_binding_deadline(self):
        expiry = QuotaReservation.objects.get().expires_at
        with patch('django.utils.timezone.now', return_value=expiry):
            self.assertEqual(self.prepare().kind, 'not_executable')
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)
