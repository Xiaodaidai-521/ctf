"""M0 behaviour tests: hard constraints and the assess_risk decision paths."""

import unittest

from export_risk.contracts import (
    AuthorizationResult,
    AuthorizationSnapshot,
    ExportRequestSnapshot,
    QualityState,
    RecommendedAction,
    SensitivityProfileRef,
    SourceMode,
)
from export_risk.contracts import reason_codes as rc
from export_risk.judgment import assess_risk


def make_request(scope=("obj1",), operation="export", recipient="rcpt1", env="production", asset="v1"):
    return ExportRequestSnapshot(
        request_id="r1", revision="1", subject_id="u1", asset_version=asset,
        scope=scope, operation=operation, recipient_id=recipient, environment=env,
        request_fingerprint="fp1", source_mode=SourceMode.SYNTHETIC,
    )


def make_auth(result=AuthorizationResult.AUTHORIZED, recipients=("rcpt1",),
              operations=("export",), scope=("obj1", "obj2"), env="production"):
    return AuthorizationSnapshot(
        authority_source="authsrc", snapshot_id="s1", subject_id="u1", data_domain="d1",
        result=result, allowed_recipients=recipients, allowed_operations=operations,
        allowed_scope=scope, environment=env, source_mode=SourceMode.SYNTHETIC,
        observed_at="2020-01-01T00:00:00+08:00", valid_until="2027-01-01T00:00:00+08:00",
    )


def make_profile(coverage=QualityState.OK, status="complete", asset="v1"):
    return SensitivityProfileRef(
        profile_id="p1", asset_version=asset, protection_level="medium",
        coverage=coverage, status=status, source_mode=SourceMode.SYNTHETIC,
    )


def run(req, auth, profile):
    return assess_risk(req, profile, auth, None, "model-m0", "policy-m0", "2026-10-11T00:00:00+08:00")


class JudgmentCoreTests(unittest.TestCase):
    def test_authorized_clean_allows(self):
        res = run(make_request(), make_auth(), make_profile())
        self.assertEqual(res.recommended_action, RecommendedAction.ALLOW)
        self.assertIn(rc.BASELINE_WITHIN_AUTHORIZED, res.reason_codes)
        self.assertFalse(res.hard_constraint_triggered)

    def test_recipient_not_allowed_denies(self):
        # Authorized result, but recipient outside the authorized envelope:
        # explicit over-authorization -> deny (invariant D4), no model involved.
        res = run(make_request(recipient="outsider"), make_auth(), make_profile())
        self.assertEqual(res.recommended_action, RecommendedAction.DENY)
        self.assertTrue(res.hard_constraint_triggered)
        self.assertIn(rc.HARD_RECIPIENT_FORBIDDEN, res.reason_codes)

    def test_scope_exceeded_denies(self):
        res = run(make_request(scope=("obj1", "obj9")), make_auth(), make_profile())
        self.assertEqual(res.recommended_action, RecommendedAction.DENY)
        self.assertIn(rc.HARD_SCOPE_EXCEEDED, res.reason_codes)

    def test_forbidden_result_denies(self):
        res = run(make_request(), make_auth(result=AuthorizationResult.FORBIDDEN), make_profile())
        self.assertEqual(res.recommended_action, RecommendedAction.DENY)
        self.assertIn(rc.HARD_AUTHORIZATION_FORBIDDEN, res.reason_codes)

    def test_unknown_authorization_defers(self):
        res = run(make_request(), make_auth(result=AuthorizationResult.UNKNOWN), make_profile())
        self.assertEqual(res.recommended_action, RecommendedAction.DEFER)
        self.assertIn(rc.DEGRADE_AUTHORIZATION_UNKNOWN, res.reason_codes)

    def test_incomplete_profile_requires_approval(self):
        res = run(make_request(), make_auth(), make_profile(coverage=QualityState.MISSING, status="unknown"))
        self.assertEqual(res.recommended_action, RecommendedAction.REQUIRE_APPROVAL)
        self.assertIn(rc.DEGRADE_PROFILE_INCOMPLETE, res.reason_codes)

    def test_asset_version_mismatch_defers(self):
        res = run(make_request(asset="v1"), make_auth(), make_profile(asset="v2"))
        self.assertEqual(res.recommended_action, RecommendedAction.DEFER)
        self.assertIn(rc.CONSISTENCY_ASSET_VERSION_MISMATCH, res.reason_codes)

    def test_environment_mismatch_defers(self):
        res = run(make_request(env="production"), make_auth(env="evaluation"), make_profile())
        self.assertEqual(res.recommended_action, RecommendedAction.DEFER)
        self.assertIn(rc.CONSISTENCY_ENVIRONMENT_MISMATCH, res.reason_codes)


if __name__ == "__main__":
    unittest.main()
