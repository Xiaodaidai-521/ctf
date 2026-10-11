"""Second-round review boundary tests (R1-R5); no external probe imports."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaService
from export_risk.contracts import QualityState, RecommendedAction
from export_risk.contracts import reason_codes as rc
from export_risk.decisions import service
from export_risk.judgment import assess_risk
from export_risk.judgment.validity import authorization_validity, parse_aware_timestamp
from export_risk.models import ExecutionAuthorizationRecord
from .test_review_safeguards import _request, _auth, _profile, _features, _assess


class PermissionBoundaryTests(TestCase):
    def test_all_narrowed_lists_block_replay_with_precise_reasons(self):
        req, grant = _request(), _auth()
        decision = service.create_risk_decision(_assess(req, grant), req, idempotency_key="create")
        first = service.prepare_execution(decision.decision_id, req, grant, idempotency_key="prepare")
        self.assertEqual(first.kind, "executable")
        cases = (("allowed_scope", rc.HARD_SCOPE_EXCEEDED),
                 ("allowed_operations", rc.HARD_OPERATION_FORBIDDEN),
                 ("allowed_recipients", rc.HARD_RECIPIENT_FORBIDDEN))
        for field, reason in cases:
            with self.subTest(field=field):
                result = service.prepare_execution(decision.decision_id, req, replace(grant, **{field: ()}),
                                                   idempotency_key="prepare")
                self.assertEqual(result.kind, "not_executable")
                self.assertIn(reason, result.reason_codes)
        self.assertEqual(ExecutionAuthorizationRecord.objects.count(), 1)

    def test_environment_and_future_observation_block_first_and_replay(self):
        req, grant = _request(), _auth()
        decision = service.create_risk_decision(_assess(req, grant), req, idempotency_key="create")
        for replay in (False, True):
            if replay:
                self.assertEqual(service.prepare_execution(decision.decision_id, req, grant,
                                                           idempotency_key="prepare").kind, "executable")
            for bad in (replace(grant, environment="evaluation"),
                        replace(grant, observed_at=(timezone.now() + timedelta(minutes=1)).isoformat()),
                        replace(grant, observed_at="")):
                with self.subTest(replay=replay, snapshot=bad):
                    result = service.prepare_execution(decision.decision_id, req, bad, idempotency_key="prepare")
                    self.assertEqual(result.kind, "not_executable")


class ExecutionDeadlineTests(TestCase):
    def _prepared(self, *, grant=None, quota=False):
        req, grant = _request(), grant or _auth()
        decision = service.create_risk_decision(_assess(req, grant), req, idempotency_key="create")
        options = {"quota": QuotaService, "quota_limit": 100} if quota else {}
        authorization = service.prepare_execution(decision.decision_id, req, grant,
                                                   idempotency_key="prepare", **options)
        self.assertEqual(authorization.kind, "executable")
        return req, grant, decision, authorization

    def test_claim_never_outlives_upstream_grant(self):
        expiry = timezone.now() + timedelta(seconds=30)
        _, _, decision, authorization = self._prepared(grant=_auth(valid_until=expiry.isoformat()))
        record = ExecutionAuthorizationRecord.objects.get(authorization_id=authorization.authorization_id)
        self.assertLess(expiry, decision.valid_until)
        self.assertEqual(record.valid_until, expiry)
        self.assertEqual(parse_aware_timestamp(authorization.valid_until), expiry)
        with patch.object(service.timezone, "now", return_value=expiry):
            self.assertFalse(service.claim(authorization.authorization_id))

    def test_quota_deadline_bounds_returned_and_stored_authorization(self):
        _, _, decision, authorization = self._prepared(quota=True)
        reservation = QuotaReservation.objects.get(reservation_id=authorization.reservation_id)
        self.assertLess(reservation.expires_at, decision.valid_until)
        record = ExecutionAuthorizationRecord.objects.get(authorization_id=authorization.authorization_id)
        self.assertEqual(record.valid_until, reservation.expires_at)
        self.assertEqual(parse_aware_timestamp(authorization.valid_until), reservation.expires_at)

    def test_expired_reservation_rejected_even_when_authorization_has_later_expiry(self):
        _, _, decision, authorization = self._prepared(quota=True)
        reservation = QuotaReservation.objects.get(reservation_id=authorization.reservation_id)
        # Isolate hold re-validation from the new min-deadline protection.
        ExecutionAuthorizationRecord.objects.filter(authorization_id=authorization.authorization_id).update(
            valid_until=decision.valid_until,
        )
        with patch.object(service.timezone, "now", return_value=reservation.expires_at + timedelta(seconds=1)):
            self.assertFalse(service.claim(authorization.authorization_id))
        self.assertEqual(QuotaBucket.objects.get(pk=reservation.bucket_id).active_reserved, reservation.amount)

    def test_released_reservation_blocks_prepare_replay_even_without_quota_argument(self):
        req, grant, decision, authorization = self._prepared(quota=True)
        QuotaService.release(reservation_id=authorization.reservation_id)
        replay = service.prepare_execution(decision.decision_id, req, grant, idempotency_key="prepare")
        self.assertEqual(replay.kind, "not_executable")
        self.assertIn(rc.EXEC_RESERVATION_INVALID, replay.reason_codes)
        self.assertEqual(ExecutionAuthorizationRecord.objects.count(), 1)

    def test_expired_reservation_blocks_prepare_replay(self):
        req, grant, decision, authorization = self._prepared(quota=True)
        expiry = parse_aware_timestamp(authorization.valid_until)
        with patch.object(service.timezone, "now", return_value=expiry):
            replay = service.prepare_execution(decision.decision_id, req, grant,
                                                idempotency_key="prepare", quota=QuotaService, quota_limit=100)
        self.assertEqual(replay.kind, "not_executable")
        self.assertEqual(QuotaReservation.objects.count(), 1)

    def test_unknown_reservation_blocks_replay_and_claim_without_releasing(self):
        req, grant, decision, authorization = self._prepared(quota=True)
        QuotaService.reconcile(reservation_id=authorization.reservation_id)
        replay = service.prepare_execution(decision.decision_id, req, grant, idempotency_key="prepare")
        self.assertEqual(replay.kind, "not_executable")
        self.assertFalse(service.claim(authorization.authorization_id))
        reservation = QuotaReservation.objects.get(reservation_id=authorization.reservation_id)
        self.assertEqual(QuotaBucket.objects.get(pk=reservation.bucket_id).unknown_reserved, reservation.amount)

    def test_replay_can_shorten_but_never_extend_old_expiry(self):
        req, grant, decision, authorization = self._prepared()
        shorter = timezone.now() + timedelta(seconds=30)
        replay = service.prepare_execution(decision.decision_id, req,
                                           replace(grant, valid_until=shorter.isoformat()), idempotency_key="prepare")
        self.assertEqual(replay.authorization_id, authorization.authorization_id)
        self.assertEqual(parse_aware_timestamp(replay.valid_until), shorter)
        again = service.prepare_execution(decision.decision_id, req, grant, idempotency_key="prepare")
        self.assertEqual(parse_aware_timestamp(again.valid_until), shorter)
        with patch.object(service.timezone, "now", return_value=shorter):
            expired = service.prepare_execution(decision.decision_id, req, grant, idempotency_key="prepare")
        self.assertEqual(expired.kind, "not_executable")

    def test_valid_claim_once_still_works_with_quota(self):
        _, _, _, authorization = self._prepared(quota=True)
        self.assertTrue(service.claim(authorization.authorization_id))
        self.assertFalse(service.claim(authorization.authorization_id))

    def test_reservation_released_when_prepare_bails_after_reserve(self):
        # Review follow-up: a reserve that succeeds but is then abandoned on the
        # final expiry re-check must not leak held capacity (the whole prepare is
        # one atomic block, so a plain return would otherwise commit the hold).
        req, grant = _request(), _auth()
        decision = service.create_risk_decision(_assess(req, grant), req, idempotency_key="create")

        class _ExpiredHoldQuota:
            released = None

            def reserve(self, **kwargs):
                result = QuotaService.reserve(**kwargs)
                self.released = None
                return replace(result, expires_at=timezone.now() - timedelta(seconds=1))

            def release(self, *, reservation_id):
                self.released = reservation_id
                return QuotaService.release(reservation_id=reservation_id)

        quota = _ExpiredHoldQuota()
        result = service.prepare_execution(decision.decision_id, req, grant, idempotency_key="prepare",
                                           quota=quota, quota_limit=100)
        self.assertEqual(result.kind, "not_executable")
        self.assertIsNotNone(quota.released)
        bucket = QuotaBucket.objects.get(subject_id=req.subject_id, data_domain="default", window_key="default")
        self.assertEqual(bucket.active_reserved, 0)       # hold freed, not leaked
        self.assertEqual(QuotaReservation.objects.get(reservation_id=quota.released).state, "released")
        self.assertEqual(ExecutionAuthorizationRecord.objects.count(), 0)


class PureInputBoundaryTests(TestCase):
    def test_timezone_parser_rejects_naive_blank_and_malformed(self):
        for value in ("", "invalid", "2026-10-11T00:00:00", "2026-10-11", None):
            with self.subTest(value=value):
                self.assertIsNone(parse_aware_timestamp(value))
        self.assertEqual(parse_aware_timestamp("2026-10-11T00:00:00Z"),
                         parse_aware_timestamp("2026-10-11T08:00:00+08:00"))

    def test_all_authorization_times_must_be_aware_and_present(self):
        req, grant = _request(), _auth()
        for field in ("observed_at", "valid_until"):
            for bad in ("", "broken", "2026-10-11T00:00:00"):
                with self.subTest(field=field, value=bad):
                    result = assess_risk(req, _profile(), replace(grant, **{field: bad}), _features(),
                                         "m", "policy-m0", timezone.now().isoformat())
                    self.assertEqual(result.recommended_action, RecommendedAction.DEFER)
                    self.assertIn(rc.DEGRADE_AUTHORIZATION_VALIDITY_UNKNOWN, result.reason_codes)

    def test_equivalent_offsets_are_valid_and_expiry_is_exclusive(self):
        evaluated = "2026-10-11T08:00:00+08:00"
        grant = _auth(observed_at="2026-10-10T23:59:00Z", valid_until="2026-10-11T00:00:01Z")
        self.assertIsNone(authorization_validity(grant, evaluated))
        expired = replace(grant, valid_until="2026-10-11T00:00:00Z")
        self.assertEqual(authorization_validity(expired, evaluated), rc.DEGRADE_AUTHORIZATION_EXPIRED)

    def test_missing_snapshot_depends_on_policy_requirements(self):
        req, grant = _request(), _auth()
        with self.assertNumQueries(0):
            for policy in ("B-v1", "C-v1", "D-v1"):
                with self.subTest(policy=policy):
                    result = assess_risk(req, _profile(), grant, None, "m", policy, timezone.now().isoformat())
                    self.assertEqual(result.input_quality, QualityState.MISSING)
                    self.assertEqual(result.recommended_action, RecommendedAction.DEFER)
                    self.assertIn(rc.DEGRADE_FEATURES_MISSING, result.reason_codes)
            for policy in ("policy-m0", "A-v1"):
                with self.subTest(policy=policy):
                    result = assess_risk(req, _profile(), grant, None, "m", policy, timezone.now().isoformat())
                    self.assertEqual(result.recommended_action, RecommendedAction.ALLOW)
                    self.assertNotIn(rc.DEGRADE_FEATURES_MISSING, result.reason_codes)
