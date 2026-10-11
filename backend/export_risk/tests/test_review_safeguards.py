"""Review remediation safeguards (F1-F13): promoted adversarial counterexamples.

Each test asserts a protection the external review (docs/mainline2-handoff-review.md)
found missing in b978b8d7 and that this change restores. These are the review's
isolated probes, re-expressed against the normal Django test runner so a
regression here fails the suite instead of only a side script.
"""

from dataclasses import replace
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from export_risk import models as rm
from export_risk.adapters.behavior import DjangoBehaviorProvider
from export_risk.baselines import Observation, build_baseline, compute_deviations
from export_risk.contracts import (
    AuthorizationResult, AuthorizationSnapshot, ExportRequestSnapshot, FeatureSnapshot,
    QualityState, RecommendedAction, SensitivityProfileRef, SourceMode,
)
from export_risk.decisions import (
    AssessmentBindingError, InMemoryApprovalProvider, claim, consume,
    create_risk_decision, invalidate_decision, prepare_execution,
)
from export_risk.features import EventRecord, build_feature_snapshot
from export_risk.judgment import assess_risk
from export_quota.services import QuotaService

def _request(subject="u1", fp="rfp", records=10, mode=SourceMode.PRODUCTION, env="production"):
    return ExportRequestSnapshot(
        request_id="req-1", revision="1", subject_id=subject, asset_version="v1",
        scope=("o1",), operation="export", recipient_id="rc1", record_count=records,
        request_fingerprint=fp, environment=env, source_mode=mode,
    )


def _auth(subject="u1", mode=SourceMode.PRODUCTION, env="production",
          result=AuthorizationResult.AUTHORIZED, valid_until=None, observed_at=None):
    now = timezone.now()
    return AuthorizationSnapshot(
        authority_source="src", snapshot_id="s1", subject_id=subject, data_domain="d1",
        result=result, allowed_scope=("o1",), allowed_operations=("export",),
        allowed_recipients=("rc1",),
        observed_at=observed_at if observed_at is not None else (now - timedelta(hours=1)).isoformat(),
        valid_until=valid_until if valid_until is not None else (now + timedelta(hours=1)).isoformat(),
        environment=env, source_mode=mode,
    )


def _profile(mode=SourceMode.PRODUCTION):
    return SensitivityProfileRef(profile_id="p1", asset_version="v1", protection_level="low",
                                 coverage=QualityState.OK, status="complete", source_mode=mode)


def _features():
    return FeatureSnapshot(feature_set_version="fs", as_of_time=timezone.now().isoformat(),
                           values={"req_count_long": 0.0}, quality=QualityState.OK)


def _assess(request, auth, profile=None, features=None, policy="policy-m0"):
    return assess_risk(request, profile or _profile(), auth, features or _features(),
                       "model", policy, timezone.now().isoformat())


class CoreAuthorizationBindingTests(TestCase):
    """F2 / F13: the pure core binds subject + validity and preserves quality."""

    def test_core_rejects_other_subject_authorization(self):
        res = _assess(_request(subject="u1"), _auth(subject="someone-else"))
        self.assertNotEqual(res.recommended_action, RecommendedAction.ALLOW)

    def test_core_rejects_expired_authorization(self):
        past = (timezone.now() - timedelta(days=1)).isoformat()
        res = _assess(_request(), _auth(valid_until=past))
        self.assertEqual(res.recommended_action, RecommendedAction.DEFER)

    def test_core_blank_validity_is_not_valid_forever(self):
        res = _assess(_request(), _auth(valid_until=""))
        self.assertEqual(res.recommended_action, RecommendedAction.DEFER)

    def test_core_naive_validity_is_not_absolute_time(self):
        naive = timezone.now().replace(tzinfo=None)
        auth = _auth(observed_at=(naive - timedelta(minutes=1)).isoformat(),
                     valid_until=(naive + timedelta(hours=1)).isoformat())
        res = assess_risk(_request(), _profile(), auth, _features(), "model", "policy-m0",
                          naive.isoformat())
        self.assertEqual(res.recommended_action, RecommendedAction.DEFER)

    def test_core_preserves_stale_feature_quality(self):
        stale = replace(_features(), quality=QualityState.STALE, missing=("req_count_long",))
        res = _assess(_request(), _auth(), features=stale, policy="B-v1")
        self.assertNotEqual(res.input_quality, QualityState.OK)


class ExecutionRecheckTests(TestCase):
    """F1: prepare re-checks the fresh snapshot and approval on first + replay."""

    def test_prepare_rechecks_forbidden_authorization(self):
        req = _request()
        d = create_risk_decision(_assess(req, _auth()), req, idempotency_key="k1")
        res = prepare_execution(d.decision_id, req, _auth(result=AuthorizationResult.FORBIDDEN),
                                idempotency_key="p1", environment="production")
        self.assertEqual(res.kind, "not_executable")

    def test_first_prepare_rejects_narrowed_scope(self):
        req = _request()
        d = create_risk_decision(_assess(req, _auth()), req, idempotency_key="k-scope")
        narrowed = replace(_auth(), allowed_scope=())
        res = prepare_execution(d.decision_id, req, narrowed, idempotency_key="p-scope")
        self.assertEqual(res.kind, "not_executable")

    def test_first_prepare_rejects_narrowed_operation(self):
        req = _request()
        d = create_risk_decision(_assess(req, _auth()), req, idempotency_key="k-op")
        narrowed = replace(_auth(), allowed_operations=())
        res = prepare_execution(d.decision_id, req, narrowed, idempotency_key="p-op")
        self.assertEqual(res.kind, "not_executable")

    def test_first_prepare_rejects_narrowed_recipient(self):
        req = _request()
        d = create_risk_decision(_assess(req, _auth()), req, idempotency_key="k-rec")
        narrowed = replace(_auth(), allowed_recipients=())
        res = prepare_execution(d.decision_id, req, narrowed, idempotency_key="p-rec")
        self.assertEqual(res.kind, "not_executable")

    def test_replay_rejects_narrowed_recipient(self):
        req = _request()
        auth_snapshot = _auth()
        d = create_risk_decision(_assess(req, auth_snapshot), req, idempotency_key="k-replay")
        first = prepare_execution(d.decision_id, req, auth_snapshot, idempotency_key="p-replay")
        self.assertEqual(first.kind, "executable")
        narrowed = replace(auth_snapshot, allowed_recipients=())
        replay = prepare_execution(d.decision_id, req, narrowed, idempotency_key="p-replay")
        self.assertEqual(replay.kind, "not_executable")

    def test_replay_rechecks_revoked_approval(self):
        req = _request(mode=SourceMode.SYNTHETIC, env="test")
        assessment = replace(_assess(req, _auth(mode=SourceMode.SYNTHETIC, env="test")),
                             recommended_action=RecommendedAction.REQUIRE_APPROVAL)
        d = create_risk_decision(assessment, req, idempotency_key="k2")
        appr = InMemoryApprovalProvider()
        appr.set_status(d.decision_id, "approved")
        snap = _auth(mode=SourceMode.SYNTHETIC, env="test")
        first = prepare_execution(d.decision_id, req, snap, idempotency_key="p2",
                                  environment="test", approval=appr)
        self.assertEqual(first.kind, "executable")
        appr.set_status(d.decision_id, "revoked")
        replay = prepare_execution(d.decision_id, req, snap, idempotency_key="p2",
                                   environment="test", approval=appr)
        self.assertEqual(replay.kind, "not_executable")


class ClaimLifecycleTests(TestCase):
    """F3: claim re-checks expiry, parent decision and reservation; consumed replay blocked."""

    def _authorize(self):
        req = _request()
        d = create_risk_decision(_assess(req, _auth()), req, idempotency_key="k-rfp")
        auth = prepare_execution(d.decision_id, req, _auth(), idempotency_key="p-rfp",
                                 environment="production")
        return req, d, auth

    def test_claim_rejects_expiration(self):
        from unittest.mock import patch
        from export_risk.decisions import service
        _, _, auth = self._authorize()
        with patch.object(service.timezone, "now", return_value=timezone.now() + timedelta(days=1)):
            self.assertFalse(claim(auth.authorization_id))

    def test_claim_rejects_invalidated_decision(self):
        _, d, auth = self._authorize()
        invalidate_decision(d.decision_id)
        self.assertFalse(claim(auth.authorization_id))

    def test_claim_rejects_released_reservation(self):
        req = _request()
        d = create_risk_decision(_assess(req, _auth()), req, idempotency_key="kq")
        auth = prepare_execution(d.decision_id, req, _auth(), idempotency_key="pq",
                                 environment="production", quota=QuotaService, quota_limit=100)
        QuotaService.release(reservation_id=auth.reservation_id)
        self.assertFalse(claim(auth.authorization_id))

    def test_claim_rejects_reservation_at_expiry_boundary(self):
        from unittest.mock import patch
        from export_risk.decisions import service
        req = _request()
        d = create_risk_decision(_assess(req, _auth()), req, idempotency_key="k-boundary")
        auth = prepare_execution(d.decision_id, req, _auth(), idempotency_key="p-boundary",
                                 quota=QuotaService, quota_limit=100)
        from export_quota.models import QuotaReservation
        expiry = QuotaReservation.objects.get(reservation_id=auth.reservation_id).expires_at
        with patch.object(service.timezone, "now", return_value=expiry):
            self.assertFalse(claim(auth.authorization_id))

    def test_consumed_authorization_not_reported_executable(self):
        req, d, auth = self._authorize()
        self.assertTrue(claim(auth.authorization_id))
        self.assertTrue(consume(auth.authorization_id))
        replay = prepare_execution(d.decision_id, req, _auth(), idempotency_key="p-rfp",
                                   environment="production")
        self.assertEqual(replay.kind, "not_executable")


class ProductionAdmissionTests(TestCase):
    """F4 / F5: production authority + decision origin + assessment binding."""

    def test_production_rejects_test_approval_provider(self):
        req = _request()
        assessment = replace(_assess(req, _auth()), recommended_action=RecommendedAction.REQUIRE_APPROVAL)
        d = create_risk_decision(assessment, req, idempotency_key="k1")
        appr = InMemoryApprovalProvider()
        self.assertFalse(appr.is_production_authority)
        appr.set_status(d.decision_id, "approved")
        res = prepare_execution(d.decision_id, req, _auth(), idempotency_key="p1",
                                environment="production", approval=appr)
        self.assertEqual(res.kind, "not_executable")

    def test_production_rejects_synthetic_decision(self):
        syn = _request(mode=SourceMode.SYNTHETIC, env="evaluation")
        d = create_risk_decision(_assess(syn, _auth(mode=SourceMode.SYNTHETIC, env="evaluation")),
                                 syn, idempotency_key="k2")
        res = prepare_execution(d.decision_id, _request(), _auth(), idempotency_key="p2",
                                environment="production")
        self.assertEqual(res.kind, "not_executable")

    def test_production_rejects_synthetic_profile_decision(self):
        # Even with a production request and grant, a synthetic/evaluation
        # sensitivity profile makes the decision non-production and unsignable.
        req, grant = _request(), _auth()
        assessment = _assess(req, grant, profile=_profile(mode=SourceMode.SYNTHETIC))
        d = create_risk_decision(assessment, req, idempotency_key="k-synprof")
        res = prepare_execution(d.decision_id, req, grant, idempotency_key="p-synprof",
                                environment="production")
        self.assertEqual(res.kind, "not_executable")

    def test_create_rejects_assessment_for_other_request(self):
        req = _request()
        assessment = _assess(req, _auth())
        other = replace(req, request_id="other", request_fingerprint="other-fp")
        with self.assertRaises(AssessmentBindingError):
            create_risk_decision(assessment, other, idempotency_key="k3")


class BehaviorInputTests(TestCase):
    """F9 / F10 / F11 / F12: dual-time, event selection, simulated isolation, cohort cold-start."""

    def test_late_received_event_excluded_from_historical_inputs(self):
        now = timezone.now()
        rm.BehaviorEvent.objects.create(
            event_id="late", subject_id="u1", event_type="export_request",
            occurred_at=now - timedelta(minutes=1), received_at=now + timedelta(hours=1), source="t")
        events = DjangoBehaviorProvider().fetch_events("u1", now)
        snap = build_feature_snapshot(events, [], now, now)
        self.assertEqual(snap.values["req_count_long"], 0.0)

    def test_simulated_behavior_excluded_by_default(self):
        now = timezone.now()
        rm.BehaviorEvent.objects.create(
            event_id="sim", subject_id="u1", event_type="export_request",
            occurred_at=now - timedelta(minutes=1), received_at=now - timedelta(seconds=30),
            source="t", is_simulated=True)
        events = DjangoBehaviorProvider().fetch_events("u1", now)
        snap = build_feature_snapshot(events, [], now, now)
        self.assertEqual(snap.values["req_count_long"], 0.0)

    def test_request_count_does_not_count_lifecycle_events(self):
        now = timezone.now()
        events = [EventRecord(str(i), kind, now - timedelta(minutes=1), now - timedelta(seconds=30))
                  for i, kind in enumerate(("export_request", "denial", "delivery", "share_access"))]
        snap = build_feature_snapshot(events, [], now, now)
        self.assertEqual(snap.values["req_count_long"], 1.0)

    def test_complete_cohort_baseline_usable_for_zero_history_user(self):
        now = timezone.now()
        obs = [Observation(f"peer-{i}", "cohort", now - timedelta(days=1), {"req_count_long": float(i % 5)})
               for i in range(25)]
        bundle = build_baseline(obs, subject_id="new-user", cohort_key="cohort", cutoff=now,
                                feature_names=("req_count_long",))
        self.assertEqual(bundle.baseline.scope, "cohort")
        self.assertTrue(bundle.usable)
        self.assertTrue(bundle.cold_start)
        self.assertTrue(compute_deviations(bundle, {"req_count_long": 100.0}))


class PositiveControlTests(TestCase):
    """Controls the review added and confirmed; kept to guard the good behaviour."""

    def test_outbox_failure_rolls_back_and_retries_once(self):
        from unittest.mock import patch
        from audit.models import AuditLedgerEntry
        from export_risk.decisions import outbox
        req = _request()
        create_risk_decision(_assess(req, _auth()), req, idempotency_key="k1")
        with patch.object(rm.EventOutbox, "save", side_effect=RuntimeError("boom after ledger append")):
            with self.assertRaises(RuntimeError):
                outbox.relay_pending()
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)
        self.assertEqual(rm.EventOutbox.objects.filter(status="pending").count(), 1)
        self.assertEqual(outbox.relay_pending(), 1)
        self.assertEqual(AuditLedgerEntry.objects.count(), 1)

    def test_core_performs_zero_database_queries(self):
        req, auth, profile, features = _request(), _auth(), _profile(), _features()
        with self.assertNumQueries(0):
            res = assess_risk(req, profile, auth, features, "m", "policy-m0", timezone.now().isoformat())
        self.assertEqual(res.recommended_action, RecommendedAction.ALLOW)

    def test_absent_feature_snapshot_defers_for_cumulative_policy(self):
        req, auth = _request(), _auth()
        res = assess_risk(req, _profile(), auth, None, "m", "B-v1", timezone.now().isoformat())
        self.assertEqual(res.recommended_action, RecommendedAction.DEFER)
        self.assertEqual(res.input_quality, QualityState.MISSING)

    def test_absent_feature_snapshot_is_allowed_for_baseline_policy(self):
        req, auth = _request(), _auth()
        res = assess_risk(req, _profile(), auth, None, "m", "policy-m0", timezone.now().isoformat())
        self.assertEqual(res.recommended_action, RecommendedAction.ALLOW)
        self.assertEqual(res.input_quality, QualityState.OK)
