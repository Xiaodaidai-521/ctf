"""M3: fusion layer, four arms, base-protection floor, explanation (E8/I4/R4)."""

import unittest

from export_risk.contracts import ExportRequestSnapshot, RecommendedAction, SensitivityProfileRef
from export_risk.contracts import reason_codes as rc
from export_risk.judgment.fusion import fuse
from export_risk.policies import POLICIES, policy_hash, resolve_policy


def req(record_count=10):
    return ExportRequestSnapshot(
        request_id="r1", revision="1", subject_id="u1", asset_version="v1",
        scope=("o1",), operation="export", recipient_id="r1", record_count=record_count,
    )


def profile(level="medium", categories=()):
    return SensitivityProfileRef(profile_id="p1", asset_version="v1",
                                 protection_level=level, categories=categories)


def has_ob(result, oid):
    return any(o.obligation_id == oid for o in result.obligations)


class FusionTests(unittest.TestCase):
    def test_base_protection_applied_in_every_arm(self):
        # R4: the base-protection floor must appear in ALL arms, even arm A.
        prof = profile(categories=("name", "health"))
        for version in POLICIES:
            res = fuse(resolve_policy(version), req(), prof, {})
            self.assertTrue(has_ob(res, "base.mask_protected"), f"arm {version} missing base protection")
            self.assertIn(rc.FUSION_BASE_PROTECTION, res.reason_codes)

    def test_arm_a_single_threshold(self):
        res = fuse(resolve_policy("A-v1"), req(record_count=5000), profile(), {})
        self.assertEqual(res.action, RecommendedAction.REQUIRE_APPROVAL)
        self.assertIn(rc.FUSION_SINGLE_THRESHOLD, res.reason_codes)

    def test_arm_a_below_threshold_allows(self):
        res = fuse(resolve_policy("A-v1"), req(record_count=10), profile(), {})
        self.assertEqual(res.action, RecommendedAction.ALLOW)

    def test_arm_b_cumulative_exceeded(self):
        res = fuse(resolve_policy("B-v1"), req(), profile(), {"req_count_long": 80.0})
        self.assertEqual(res.action, RecommendedAction.REQUIRE_APPROVAL)
        self.assertIn(rc.FUSION_CUMULATIVE_EXCEEDED, res.reason_codes)

    def test_arm_c_anomaly_high_from_deviation(self):
        res = fuse(resolve_policy("C-v1"), req(), profile(), {"dev::req_count_long": 6.0})
        self.assertEqual(res.action, RecommendedAction.REQUIRE_APPROVAL)
        self.assertIn(rc.FUSION_ANOMALY_HIGH, res.reason_codes)
        self.assertFalse(res.anomaly_component["model_available"])
        self.assertEqual(res.anomaly_component["method"], "robust_deviation_aggregate")

    def test_arm_c_model_unavailable_is_surfaced_not_silent(self):
        res = fuse(resolve_policy("C-v1"), req(), profile(), {})  # no dev/model signal
        self.assertIn(rc.FUSION_ANOMALY_MODEL_UNAVAILABLE, res.reason_codes)
        self.assertIsNone(res.anomaly_component["score"])

    def test_arm_d_sensitive_with_anomaly_strengthens(self):
        res = fuse(resolve_policy("D-v1"), req(), profile(level="high", categories=("health",)),
                   {"dev::req_count_long": 9.0})
        self.assertEqual(res.action, RecommendedAction.REQUIRE_APPROVAL)
        self.assertIn(rc.FUSION_SENSITIVE_ANOMALY, res.reason_codes)
        self.assertTrue(has_ob(res, "base.mask_protected"))
        self.assertTrue(has_ob(res, "d.sensitive_approval"))

    def test_policy_hash_deterministic_and_resolve_unknown_raises(self):
        self.assertEqual(policy_hash(resolve_policy("D-v1")), policy_hash(resolve_policy("D-v1")))
        with self.assertRaises(KeyError):
            resolve_policy("does-not-exist")


if __name__ == "__main__":
    unittest.main()
