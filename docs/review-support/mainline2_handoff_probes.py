"""Independent review probes: isolated SQLite memory, no project settings/data.

Run with the project's Django dependencies installed:
    python docs/review-support/mainline2_handoff_probes.py

Assertions describe expected safeguards. A failure is a review counterexample,
not a passing regression. This file is outside normal Django test discovery.
"""

import io
import json
import sys
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from django.conf import settings

settings.configure(
    SECRET_KEY="isolated-mainline2-review",
    INSTALLED_APPS=[
        "django.contrib.auth", "django.contrib.contenttypes", "users", "audit",
        "export_quota", "export_risk",
    ],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    AUTH_USER_MODEL="users.CTFUser",
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    USE_TZ=True,
)

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from audit.models import AuditLedgerEntry, AuditLedgerLock
from export_quota.models import QuotaBucket, QuotaReservation
from export_quota.services import QuotaError, QuotaService
from export_risk import models as rm
from export_risk.adapters.behavior import DjangoBehaviorProvider
from export_risk.baselines import Observation, build_baseline, compute_deviations
from export_risk.contracts import (
    AuthorizationResult, AuthorizationSnapshot, ExportRequestSnapshot,
    FeatureSnapshot, QualityState, RecommendedAction, SensitivityProfileRef,
    SourceMode,
)
from export_risk.decisions import InMemoryApprovalProvider, outbox, service
from export_risk.features import EventRecord, build_feature_snapshot
from export_risk.judgment import assess_risk

NOW = timezone.now()
BUCKET = {"subject_id": "review-user", "data_domain": "review-domain", "window_key": "review-window"}


def inputs(mode=SourceMode.PRODUCTION, environment="production"):
    request = ExportRequestSnapshot(
        request_id="review-request", revision="1", subject_id="review-user",
        asset_version="review-asset-v1", scope=("object-1",), operation="export",
        recipient_id="review-recipient", record_count=10,
        request_fingerprint="review-fingerprint", environment=environment, source_mode=mode,
    )
    auth = AuthorizationSnapshot(
        authority_source="review-authority", snapshot_id="review-auth-snapshot",
        subject_id=request.subject_id, data_domain="review-domain",
        result=AuthorizationResult.AUTHORIZED, allowed_scope=request.scope,
        allowed_operations=(request.operation,), allowed_recipients=(request.recipient_id,),
        observed_at=(NOW - timedelta(minutes=1)).isoformat(),
        valid_until=(NOW + timedelta(hours=1)).isoformat(),
        environment=environment, source_mode=mode,
    )
    profile = SensitivityProfileRef(
        profile_id="review-profile", asset_version=request.asset_version,
        protection_level="low", coverage=QualityState.OK, status="complete", source_mode=mode,
    )
    features = FeatureSnapshot(feature_set_version="review-features", as_of_time=NOW.isoformat(),
                               values={"req_count_long": 0.0}, quality=QualityState.OK)
    return request, auth, profile, features


def assess(parts, policy="policy-m0"):
    request, auth, profile, features = parts
    return assess_risk(request, profile, auth, features, "review-model", policy, NOW.isoformat())


def decision(parts=None, key="create", assessment=None):
    parts = parts or inputs()
    return service.create_risk_decision(assessment or assess(parts), parts[0], idempotency_key=key)


def reserve(rid="review-reservation", amount=60, fingerprint="fp", bucket=None):
    return QuotaService.reserve(**(bucket or BUCKET), amount=amount,
                                request_fingerprint=fingerprint, reservation_id=rid, limit=100)


class SafeguardProbes(TestCase):
    def test_core_rejects_other_subject_authorization(self):
        request, auth, profile, features = inputs()
        result = assess((request, replace(auth, subject_id="other-user"), profile, features))
        self.assertNotEqual(result.recommended_action, RecommendedAction.ALLOW,
                            "another subject's authorization produced allow")

    def test_core_rejects_expired_authorization(self):
        request, auth, profile, features = inputs()
        result = assess((request, replace(auth, valid_until=(NOW - timedelta(days=1)).isoformat()), profile, features))
        self.assertNotEqual(result.recommended_action, RecommendedAction.ALLOW,
                            "authorization expired before evaluation_time produced allow")

    def test_prepare_rechecks_forbidden_authorization(self):
        parts = inputs()
        d = decision(parts)
        result = service.prepare_execution(d.decision_id, parts[0],
            replace(parts[1], result=AuthorizationResult.FORBIDDEN), idempotency_key="prepare")
        self.assertEqual(result.kind, "not_executable", "forbidden snapshot produced executable")

    def test_replay_rechecks_revoked_approval(self):
        parts = inputs(SourceMode.SYNTHETIC, "test")
        approval = InMemoryApprovalProvider()
        d = decision(parts, assessment=replace(assess(parts), recommended_action=RecommendedAction.REQUIRE_APPROVAL))
        approval.set_status(d.decision_id, "approved")
        initial = service.prepare_execution(d.decision_id, parts[0], parts[1], idempotency_key="prepare",
                                            environment="test", approval=approval)
        self.assertEqual(initial.kind, "executable")
        approval.set_status(d.decision_id, "revoked")
        replay = service.prepare_execution(d.decision_id, parts[0], parts[1], idempotency_key="prepare",
                                           environment="test", approval=approval)
        self.assertEqual(replay.kind, "not_executable", "revoked approval still replays executable")

    def test_claim_rejects_expiration(self):
        parts = inputs()
        d = decision(parts)
        auth = service.prepare_execution(d.decision_id, parts[0], parts[1], idempotency_key="prepare")
        with patch.object(service.timezone, "now", return_value=NOW + timedelta(days=1)):
            self.assertFalse(service.claim(auth.authorization_id), "expired authorization was claimable")

    def test_claim_rejects_invalidated_decision(self):
        parts = inputs()
        d = decision(parts)
        auth = service.prepare_execution(d.decision_id, parts[0], parts[1], idempotency_key="prepare")
        service.invalidate_decision(d.decision_id)
        self.assertFalse(service.claim(auth.authorization_id), "invalidated decision's authorization was claimable")

    def test_claim_rejects_released_reservation(self):
        parts = inputs()
        d = decision(parts)
        auth = service.prepare_execution(d.decision_id, parts[0], parts[1], idempotency_key="prepare",
                                         quota=QuotaService, quota_limit=100)
        QuotaService.release(reservation_id=auth.reservation_id)
        self.assertFalse(service.claim(auth.authorization_id), "released reservation's authorization was claimable")

    def test_consumed_authorization_not_reported_executable(self):
        parts = inputs()
        d = decision(parts)
        auth = service.prepare_execution(d.decision_id, parts[0], parts[1], idempotency_key="prepare")
        self.assertTrue(service.claim(auth.authorization_id))
        self.assertTrue(service.consume(auth.authorization_id))
        replay = service.prepare_execution(d.decision_id, parts[0], parts[1], idempotency_key="prepare")
        self.assertEqual(replay.kind, "not_executable", "consumed authorization still reported executable")

    def test_production_rejects_test_approval_provider(self):
        parts = inputs()
        d = decision(parts, assessment=replace(assess(parts), recommended_action=RecommendedAction.REQUIRE_APPROVAL))
        approval = InMemoryApprovalProvider()
        self.assertFalse(approval.is_production_authority)
        approval.set_status(d.decision_id, "approved")
        result = service.prepare_execution(d.decision_id, parts[0], parts[1], idempotency_key="prepare",
                                           environment="production", approval=approval)
        self.assertEqual(result.kind, "not_executable", "production accepted non-production approval authority")

    def test_production_rejects_synthetic_decision(self):
        d = decision(inputs(SourceMode.SYNTHETIC, "evaluation"))
        prod = inputs()
        result = service.prepare_execution(d.decision_id, prod[0], prod[1], idempotency_key="prepare",
                                           environment="production")
        self.assertEqual(result.kind, "not_executable", "evaluation decision used for production signing")

    def test_create_rejects_assessment_for_other_request(self):
        parts = inputs()
        mismatch = replace(parts[0], request_id="other-request", request_fingerprint="other-fingerprint")
        try:
            created = service.create_risk_decision(assess(parts), mismatch, idempotency_key="create")
        except (ValueError, service.IdempotencyConflict):
            return
        self.fail("assessment for review-request persisted as " + created.request_id)

    def test_quota_unknown_can_be_reconciled_after_receipt(self):
        reserve()
        QuotaService.reconcile(reservation_id="review-reservation", delivered_amount=None)
        try:
            QuotaService.reconcile(reservation_id="review-reservation", delivered_amount=40)
        except QuotaError as exc:
            self.fail(str(exc))
        bucket = QuotaBucket.objects.get(**BUCKET)
        self.assertEqual((bucket.unknown_reserved, bucket.settled, bucket.available), (0, 40, 60))

    def test_quota_replay_rejects_changed_binding(self):
        reserve()
        other_bucket = {**BUCKET, "subject_id": "another-user"}
        try:
            replay = reserve(amount=90, fingerprint="different-fp", bucket=other_bucket)
        except QuotaError:
            return
        real = QuotaReservation.objects.get(reservation_id="review-reservation")
        self.fail(f"replay accepted: reported bucket={replay.bucket_id}, actual bucket={real.bucket_id}, amount={replay.amount}")

    def test_quota_rejects_negative_amount(self):
        try:
            reserve("negative", -50)
        except (QuotaError, ValueError):
            return
        reserve("positive", 150)
        self.fail("negative -50 reservation allowed a positive 150 reservation against limit 100")

    def test_quota_does_not_silently_clamp_actual_delivery(self):
        reserve(amount=60)
        try:
            QuotaService.commit(reservation_id="review-reservation", delivered_amount=90)
        except (QuotaError, ValueError):
            return
        bucket = QuotaBucket.objects.get(**BUCKET)
        self.assertEqual(bucket.settled, 90, "reported delivery 90 silently accounted as 60")

    def test_late_received_event_excluded_from_historical_inputs(self):
        rm.BehaviorEvent.objects.create(
            event_id="late", subject_id="review-user", event_type="export_request",
            occurred_at=NOW - timedelta(minutes=1), received_at=NOW + timedelta(hours=1), source="review",
        )
        events = DjangoBehaviorProvider().fetch_events("review-user", NOW)
        snap = build_feature_snapshot(events, [], NOW, NOW)
        self.assertEqual(snap.values["req_count_long"], 0.0, "historical inputs used event received one hour in the future")

    def test_request_count_does_not_count_lifecycle_events(self):
        events = [EventRecord(str(i), kind, NOW - timedelta(minutes=1), NOW - timedelta(seconds=30))
                  for i, kind in enumerate(("export_request", "denial", "delivery", "share_access"))]
        snap = build_feature_snapshot(events, [], NOW, NOW)
        self.assertEqual(snap.values["req_count_long"], 1.0, "one request plus lifecycle events counted as four requests")

    def test_simulated_behavior_excluded_by_default(self):
        rm.BehaviorEvent.objects.create(
            event_id="simulated", subject_id="review-user", event_type="export_request",
            occurred_at=NOW - timedelta(minutes=1), received_at=NOW - timedelta(seconds=30),
            source="review", is_simulated=True,
        )
        events = DjangoBehaviorProvider().fetch_events("review-user", NOW)
        snap = build_feature_snapshot(events, [], NOW, NOW)
        self.assertEqual(snap.values["req_count_long"], 0.0, "simulated event contributed to default behavior count")

    def test_complete_cohort_baseline_usable_for_zero_history_user(self):
        observations = [Observation(f"peer-{i}", "review-cohort", NOW - timedelta(days=1),
                                    {"req_count_long": float(i % 5)}) for i in range(25)]
        bundle = build_baseline(observations, subject_id="new-user", cohort_key="review-cohort",
                                cutoff=NOW, feature_names=("req_count_long",))
        self.assertEqual(bundle.baseline.scope, "cohort")
        self.assertTrue(bundle.usable, "25 cohort samples still marked unusable for a zero-history user")
        self.assertTrue(compute_deviations(bundle, {"req_count_long": 100.0}))

    def test_core_preserves_stale_feature_quality(self):
        request, auth, profile, features = inputs()
        stale = replace(features, quality=QualityState.STALE, missing=("req_count_long",))
        result = assess((request, auth, profile, stale), policy="B-v1")
        self.assertNotEqual(result.input_quality, QualityState.OK,
                            "STALE/missing features promoted to input_quality=OK")

    def test_control_outbox_failure_rolls_back_and_retries_once(self):
        decision()
        with patch.object(rm.EventOutbox, "save", side_effect=RuntimeError("review failure after ledger append")):
            with self.assertRaises(RuntimeError):
                outbox.relay_pending()
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)
        self.assertEqual(rm.EventOutbox.objects.filter(status="pending").count(), 1)
        self.assertEqual(outbox.relay_pending(), 1)
        self.assertEqual(outbox.relay_pending(), 0)
        self.assertEqual(AuditLedgerEntry.objects.count(), 1)

    def test_control_core_performs_zero_database_queries(self):
        with self.assertNumQueries(0):
            result = assess(inputs())
        self.assertEqual(result.recommended_action, RecommendedAction.ALLOW)


def main():
    if connection.settings_dict["NAME"] != ":memory:":
        raise RuntimeError("Review probes require an in-memory database")
    tables = [
        get_user_model(), AuditLedgerLock, AuditLedgerEntry, QuotaBucket, QuotaReservation,
        rm.BehaviorEvent, rm.ExportRequestLog, rm.DeliveryRecord, rm.RiskDecision,
        rm.IdempotencyRecord, rm.ExecutionAuthorizationRecord, rm.EventOutbox,
    ]
    with connection.schema_editor() as editor:
        for model in tables:
            editor.create_model(model)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SafeguardProbes)
    )
    issues = []
    for test, trace in result.failures + result.errors:
        detail = [line.strip() for line in trace.splitlines()
                  if line.startswith("AssertionError:") or line.lstrip().startswith(": ")]
        issues.append({"test": test._testMethodName,
                       "error": " ".join(detail) if detail else trace.strip().splitlines()[-1]})
    print(json.dumps({
        "django": django.get_version(), "database": ":memory:", "tests": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "passed": result.testsRun - len(result.failures) - len(result.errors), "issues": issues,
    }, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
