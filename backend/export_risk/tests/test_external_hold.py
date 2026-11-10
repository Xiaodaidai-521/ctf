"""Flow-owned holds: risk checks eligibility but never owns reserve/release."""
from datetime import timedelta
from unittest.mock import Mock, patch

from django.db import connection
from django.test import TestCase
from django.utils import timezone

from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaService
from export_risk.contracts import RecommendedAction
from export_risk.decisions import service
from export_risk.models import ExecutionAuthorizationRecord
from export_risk.tests.test_decisions import make_assessment, make_auth_snapshot, make_request


class ExternalHoldTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        self.request = make_request()
        self.snapshot = make_auth_snapshot()
        self.decision = service.create_risk_decision(
            make_assessment(RecommendedAction.ALLOW), self.request, idempotency_key='decision/flow',
        )
        self.hold = QuotaService.reserve(subject_id='u1', data_domain='d1', window_key='flow',
            amount=10, request_fingerprint='fp1', reservation_id='reservation/flow', limit=10)
        self.active = Mock(side_effect=lambda **values: QuotaService.require_active(**values).expires_at)

    def prepare(self, **changes):
        options = dict(idempotency_key='prepare/flow', environment='test',
            reservation_id='reservation/flow', authorization_id='authorization/flow',
            execution_id='execution/flow', require_active=self.active)
        options.update(changes)
        return service.prepare_execution(self.decision.decision_id, self.request, self.snapshot, **options)

    def test_issue_replay_claim_use_injection_without_second_reserve(self):
        with patch.object(QuotaService, 'reserve', side_effect=AssertionError('second reserve')), \
                patch.object(QuotaService, 'release', side_effect=AssertionError('risk released hold')):
            auth = self.prepare()
            self.assertEqual(auth.kind, 'executable')
            self.assertEqual((auth.authorization_id, auth.execution_id, auth.reservation_id),
                ('authorization/flow', 'execution/flow', 'reservation/flow'))
            self.assertEqual(self.prepare(), auth)
            self.assertTrue(service.claim(auth.authorization_id, require_active=self.active))
            self.assertFalse(service.claim(auth.authorization_id, require_active=self.active))
        self.assertEqual(self.active.call_count, 3)
        self.active.assert_any_call(reservation_id='reservation/flow', request_fingerprint='fp1', amount=10)
        self.assertEqual(QuotaReservation.objects.count(), 1)
        bucket = QuotaBucket.objects.get()
        self.assertEqual((bucket.active_reserved, bucket.unknown_reserved, bucket.settled), (10, 0, 0))

    def test_missing_or_expired_hold_denies_without_releasing(self):
        for expiry in (None, timezone.now() - timedelta(seconds=1)):
            with self.subTest(expiry=expiry), patch.object(QuotaService, 'release') as release:
                result = self.prepare(require_active=Mock(return_value=expiry))
                self.assertEqual(result.kind, 'not_executable')
                self.assertIn('exec.reservation_invalid', result.reason_codes)
                release.assert_not_called()
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_external_hold_cannot_be_mixed_with_legacy_quota(self):
        with self.assertRaises(ValueError):
            self.prepare(quota=QuotaService)
        with self.assertRaises(ValueError):
            self.prepare(require_active=service._legacy_require_active)
        self.assertFalse(ExecutionAuthorizationRecord.objects.exists())

    def test_replay_binds_all_flow_identities(self):
        self.prepare()
        for key in ('reservation_id', 'authorization_id', 'execution_id'):
            with self.subTest(key=key), self.assertRaises(service.IdempotencyConflict):
                self.prepare(**{key: 'other/identity'})
        self.assertEqual(ExecutionAuthorizationRecord.objects.count(), 1)

    def test_claim_uses_injected_rejection_without_fallback(self):
        auth = self.prepare()
        reject = Mock(return_value=None)
        with patch.object(QuotaService, 'require_active', side_effect=AssertionError('fallback')):
            self.assertFalse(service.claim(auth.authorization_id, require_active=reject))
        reject.assert_called_once_with(reservation_id='reservation/flow', request_fingerprint='fp1')
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().state, 'valid')
        self.assertEqual(QuotaBucket.objects.get().active_reserved, 10)

    def test_clock_is_rechecked_after_injected_wait(self):
        auth = self.prepare()
        before = timezone.now()
        after = self.hold.expires_at + timedelta(seconds=1)
        clock = [before]

        def waited(**values):
            clock[0] = after
            return self.hold.expires_at

        with patch.object(service.timezone, 'now', side_effect=lambda: clock[0]):
            self.assertFalse(service.claim(auth.authorization_id, require_active=waited))
        self.assertEqual(QuotaReservation.objects.get().state, 'reserved')

    def test_shorter_live_hold_tightens_authorization(self):
        auth = self.prepare()
        shorter = timezone.now() + timedelta(seconds=30)
        again = self.prepare(require_active=Mock(return_value=shorter))
        self.assertLess(again.valid_until, auth.valid_until)
        self.assertEqual(ExecutionAuthorizationRecord.objects.get().valid_until, shorter)
