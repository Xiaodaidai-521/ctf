"""M4: decision persistence, idempotency, admission, approval, quota, state machine."""

from django.test import TestCase

from export_risk.contracts import (
    AuthorizationResult,
    AuthorizationSnapshot,
    Disposition,
    ExportRequestSnapshot,
    ExportRiskAssessment,
    Obligation,
    RecommendedAction,
    SourceMode,
)
from export_risk.contracts import reason_codes as rc
from export_risk import decisions
from export_risk.decisions import service
from export_risk.models import EventOutbox, RiskDecision


def make_request(fp="fp1", records=10, mode=SourceMode.SYNTHETIC, env="test"):
    return ExportRequestSnapshot(
        request_id="r1", revision="1", subject_id="u1", asset_version="v1", scope=("o1",),
        operation="export", recipient_id="rc1", record_count=records, request_fingerprint=fp,
        environment=env, source_mode=mode,
    )


def make_assessment(action, obligations=(), policy="D-v1"):
    return ExportRiskAssessment(
        request_id="r1", request_fingerprint="fp1", recommended_action=action,
        obligations=obligations, policy_version=policy, profile_id="p1",
    )


def make_auth_snapshot(mode=SourceMode.SYNTHETIC, env="test"):
    return AuthorizationSnapshot(
        authority_source="src", snapshot_id="s1", subject_id="u1", data_domain="d1",
        result=AuthorizationResult.AUTHORIZED, environment=env, source_mode=mode,
    )


class DecisionPersistenceTests(TestCase):
    def test_create_is_idempotent_on_key(self):
        a = make_assessment(RecommendedAction.ALLOW)
        d1 = decisions.create_risk_decision(a, make_request(), idempotency_key="k1")
        d2 = decisions.create_risk_decision(a, make_request(), idempotency_key="k1")
        self.assertEqual(d1.decision_id, d2.decision_id)
        self.assertEqual(RiskDecision.objects.count(), 1)

    def test_same_key_different_request_conflicts(self):
        decisions.create_risk_decision(make_assessment(RecommendedAction.ALLOW), make_request(), idempotency_key="k1")
        with self.assertRaises(service.IdempotencyConflict):
            decisions.create_risk_decision(make_assessment(RecommendedAction.DENY), make_request(), idempotency_key="k1")

    def test_decision_issued_event_enqueued(self):
        decisions.create_risk_decision(make_assessment(RecommendedAction.ALLOW), make_request(), idempotency_key="k1")
        self.assertTrue(EventOutbox.objects.filter(event_type="decision.issued").exists())

    def test_admission_rejects_synthetic_in_production(self):
        a = make_assessment(RecommendedAction.ALLOW)
        d = decisions.create_risk_decision(a, make_request(), idempotency_key="k1")
        result = decisions.prepare_execution(
            d.decision_id, make_request(mode=SourceMode.SYNTHETIC), make_auth_snapshot(),
            idempotency_key="pk1", environment="production",
        )
        self.assertEqual(result.kind, "not_executable")
        self.assertEqual(result.disposition, Disposition.DENY)
        self.assertIn(rc.ADMISSION_SYNTHETIC_IN_PRODUCTION, result.reason_codes)

class PrepareExecutionTests(TestCase):
    def _decision(self, action, obligations=()):
        return decisions.create_risk_decision(
            make_assessment(action, obligations), make_request(), idempotency_key="k1"
        )

    def test_allow_yields_authorization_and_event(self):
        d = self._decision(RecommendedAction.ALLOW)
        result = decisions.prepare_execution(
            d.decision_id, make_request(), make_auth_snapshot(), idempotency_key="pk1", environment="test"
        )
        self.assertEqual(result.kind, "executable")
        self.assertEqual(result.decision_id, d.decision_id)
        self.assertTrue(EventOutbox.objects.filter(event_type="execution.authorized").exists())

    def test_require_approval_gate(self):
        from export_risk.decisions import InMemoryApprovalProvider
        d = self._decision(RecommendedAction.REQUIRE_APPROVAL)
        appr = InMemoryApprovalProvider()
        blocked = decisions.prepare_execution(
            d.decision_id, make_request(), make_auth_snapshot(), idempotency_key="pk1",
            environment="test", approval=appr,
        )
        self.assertEqual(blocked.disposition, Disposition.REQUIRE_APPROVAL)
        appr.set_status(d.decision_id, "approved")
        ok = decisions.prepare_execution(
            d.decision_id, make_request(), make_auth_snapshot(), idempotency_key="pk1",
            environment="test", approval=appr,
        )
        self.assertEqual(ok.kind, "executable")

    def test_deny_decision_not_executable(self):
        d = self._decision(RecommendedAction.DENY)
        result = decisions.prepare_execution(
            d.decision_id, make_request(), make_auth_snapshot(), idempotency_key="pk1", environment="test"
        )
        self.assertEqual(result.disposition, Disposition.DENY)
        self.assertIn(rc.EXEC_ACTION_DENY, result.reason_codes)

    def test_quota_exceeded_defers(self):
        from export_quota.services import QuotaService
        d = self._decision(RecommendedAction.ALLOW)
        result = decisions.prepare_execution(
            d.decision_id, make_request(records=60), make_auth_snapshot(), idempotency_key="pk1",
            environment="test", quota=QuotaService, quota_limit=50,
        )
        self.assertEqual(result.disposition, Disposition.DEFER)
        self.assertIn(rc.EXEC_QUOTA_EXCEEDED, result.reason_codes)

    def test_unsupported_obligation_blocks_authorization(self):
        bad = Obligation(obligation_id="x", type="exfiltrate_raw")
        d = self._decision(RecommendedAction.ALLOW, obligations=(bad,))
        result = decisions.prepare_execution(
            d.decision_id, make_request(), make_auth_snapshot(), idempotency_key="pk1", environment="test"
        )
        self.assertEqual(result.disposition, Disposition.REQUIRE_APPROVAL)
        self.assertIn(rc.EXEC_OBLIGATION_UNSUPPORTED, result.reason_codes)

class StateMachineAndOutboxTests(TestCase):
    def _authorize(self):
        d = decisions.create_risk_decision(
            make_assessment(RecommendedAction.ALLOW), make_request(), idempotency_key="k1"
        )
        auth = decisions.prepare_execution(
            d.decision_id, make_request(), make_auth_snapshot(), idempotency_key="pk1", environment="test"
        )
        return d, auth

    def test_idempotent_replay_returns_same_authorization(self):
        d, auth = self._authorize()
        again = decisions.prepare_execution(
            d.decision_id, make_request(), make_auth_snapshot(), idempotency_key="pk1", environment="test"
        )
        self.assertEqual(again.authorization_id, auth.authorization_id)

    def test_replay_after_revoke_is_not_executable(self):
        # Review R1: same key replays the id but re-checks live state -> blocked.
        d, auth = self._authorize()
        decisions.revoke_authorization(auth.authorization_id)
        result = decisions.prepare_execution(
            d.decision_id, make_request(), make_auth_snapshot(), idempotency_key="pk1", environment="test"
        )
        self.assertEqual(result.kind, "not_executable")
        self.assertIn(rc.EXEC_AUTHORIZATION_REVOKED, result.reason_codes)

    def test_single_claim_then_consume(self):
        _, auth = self._authorize()
        self.assertTrue(decisions.claim(auth.authorization_id))
        self.assertFalse(decisions.claim(auth.authorization_id))   # already claiming
        self.assertTrue(decisions.consume(auth.authorization_id))
        self.assertFalse(decisions.consume(auth.authorization_id))  # already consumed

    def test_outbox_relay_appends_audit_chain_and_is_idempotent(self):
        from export_risk.decisions import outbox
        from audit.services import AuditLedgerService
        self._authorize()  # enqueues decision.issued + execution.authorized
        relayed = outbox.relay_pending()
        self.assertEqual(relayed, 2)
        self.assertEqual(outbox.relay_pending(), 0)              # idempotent: nothing pending
        self.assertTrue(AuditLedgerService.verify_chain().is_valid)
        self.assertFalse(EventOutbox.objects.filter(status="pending").exists())


