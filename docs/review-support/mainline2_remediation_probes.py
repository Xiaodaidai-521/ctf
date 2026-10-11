"""Follow-up safeguards; imports original probes without modifying that file.

Uses only their isolated SQLite :memory: setup. Failed assertions represent
remaining counterexamples, NOT passing tests. Run from the repository root.
"""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import mainline2_handoff_probes as base


class RemediationProbes(base.TestCase):
    def _prepared(self, *, quota=False, parts=None):
        parts = parts or base.inputs()
        decision = base.decision(parts)
        options = {"quota": base.QuotaService, "quota_limit": 100} if quota else {}
        auth = base.service.prepare_execution(
            decision.decision_id, parts[0], parts[1], idempotency_key="prepare", **options
        )
        self.assertEqual(auth.kind, "executable")
        return parts, decision, auth

    def _first_prepare_rejects_narrowed_envelope(self, field):
        parts = base.inputs()
        decision = base.decision(parts)
        fresh = replace(parts[1], **{field: ()})
        self.assertEqual(base.assess((parts[0], fresh, *parts[2:])).recommended_action,
                         base.RecommendedAction.DENY)
        result = base.service.prepare_execution(
            decision.decision_id, parts[0], fresh, idempotency_key="prepare-" + field
        )
        self.assertEqual(result.kind, "not_executable", field + " narrowed but executable")

    def test_first_prepare_rejects_narrowed_scope(self):
        self._first_prepare_rejects_narrowed_envelope("allowed_scope")

    def test_first_prepare_rejects_narrowed_operations(self):
        self._first_prepare_rejects_narrowed_envelope("allowed_operations")

    def test_first_prepare_rejects_narrowed_recipients(self):
        self._first_prepare_rejects_narrowed_envelope("allowed_recipients")

    def test_replay_rejects_narrowed_recipient(self):
        parts, decision, _ = self._prepared()
        result = base.service.prepare_execution(
            decision.decision_id, parts[0], replace(parts[1], allowed_recipients=()),
            idempotency_key="prepare"
        )
        self.assertEqual(result.kind, "not_executable", "revoked recipient still replays executable")

    def test_claim_rejects_expired_reservation(self):
        _, decision, auth = self._prepared(quota=True)
        reservation = base.QuotaReservation.objects.get(reservation_id=auth.reservation_id)
        later = reservation.expires_at + timedelta(seconds=1)
        self.assertLess(later, decision.valid_until)
        with patch.object(base.service.timezone, "now", return_value=later):
            self.assertFalse(base.service.claim(auth.authorization_id), "expired reservation still claimable")

    def test_prepare_replay_rejects_released_reservation(self):
        parts, decision, auth = self._prepared(quota=True)
        base.QuotaService.release(reservation_id=auth.reservation_id)
        result = base.service.prepare_execution(
            decision.decision_id, parts[0], parts[1], idempotency_key="prepare",
            quota=base.QuotaService, quota_limit=100
        )
        self.assertEqual(result.kind, "not_executable", "released quota still replays executable")

    def test_reserve_replay_rejects_expired_reservation(self):
        base.reserve()
        reservation = base.QuotaReservation.objects.get(reservation_id="review-reservation")
        with patch.object(base.service.timezone, "now", return_value=reservation.expires_at + timedelta(seconds=1)):
            with self.assertRaises(base.QuotaError, msg="expired hold returned as active replay"):
                base.reserve()

    def test_claim_does_not_outlive_known_authorization_grant(self):
        parts = base.inputs()
        expiry = base.NOW + timedelta(seconds=30)
        parts = (parts[0], replace(parts[1], valid_until=expiry.isoformat()), *parts[2:])
        _, decision, auth = self._prepared(parts=parts)
        self.assertLess(expiry, decision.valid_until)
        with patch.object(base.service.timezone, "now", return_value=expiry + timedelta(seconds=1)):
            self.assertFalse(base.service.claim(auth.authorization_id), "claim outlives known upstream grant")

    def test_confirmed_reconcile_retry_is_idempotent(self):
        base.reserve()
        base.QuotaService.reconcile(reservation_id="review-reservation", delivered_amount=None)
        base.QuotaService.reconcile(reservation_id="review-reservation", delivered_amount=40)
        try:
            base.QuotaService.reconcile(reservation_id="review-reservation", delivered_amount=40)
        except base.QuotaError as exc:
            self.fail("same confirmed receipt cannot retry: " + str(exc))
        bucket = base.QuotaBucket.objects.get(**base.BUCKET)
        self.assertEqual((bucket.unknown_reserved, bucket.settled, bucket.available), (0, 40, 60))

    def test_absent_feature_snapshot_is_not_quality_ok(self):
        parts = base.inputs()
        result = base.assess((*parts[:3], None), policy="B-v1")
        self.assertNotEqual(result.input_quality, base.QualityState.OK,
                            "absent features marked OK; action=" + result.recommended_action.value)

    def test_core_rejects_all_naive_authorization_times(self):
        request, auth, profile, features = base.inputs()
        naive = base.NOW.replace(tzinfo=None)
        auth = replace(auth, observed_at=(naive - timedelta(minutes=1)).isoformat(),
                       valid_until=(naive + timedelta(minutes=1)).isoformat())
        result = base.assess_risk(request, profile, auth, features, "review-model", "policy-m0", naive.isoformat())
        self.assertEqual(result.recommended_action, base.RecommendedAction.DEFER,
                         "timezone-free validity accepted as established")

    def test_control_valid_claim_still_works(self):
        _, _, auth = self._prepared(quota=True)
        self.assertTrue(base.service.claim(auth.authorization_id))
        self.assertFalse(base.service.claim(auth.authorization_id))


if __name__ == "__main__":
    # Reuse only the setup/runner; the original 22 tests remain unmodified.
    base.SafeguardProbes = RemediationProbes
    raise SystemExit(base.main())
