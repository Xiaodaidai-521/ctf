"""R7 immutability: frozen dataclasses + recursive deep-freeze of nested fields."""

import unittest
from types import MappingProxyType

from export_risk.contracts import (
    AuthorizationResult,
    AuthorizationSnapshot,
    ExportRequestSnapshot,
    FeatureSnapshot,
    SourceMode,
)


def _request(scope):
    return ExportRequestSnapshot(
        request_id="r1", revision="1", subject_id="u1", asset_version="v1",
        scope=scope, operation="export", recipient_id="rcpt1",
        source_mode=SourceMode.SYNTHETIC,
    )


class ImmutabilityTests(unittest.TestCase):
    def test_frozen_field_rebind_blocked(self):
        req = _request(["a", "b"])
        with self.assertRaises(Exception):
            req.recipient_id = "rcpt2"  # type: ignore[misc]

    def test_nested_list_mutation_does_not_leak(self):
        original = ["a", "b"]
        req = _request(original)
        original.append("c")  # mutate the caller's list after construction
        self.assertEqual(req.scope, ("a", "b"))  # snapshot unchanged
        self.assertIsInstance(req.scope, tuple)

    def test_nested_mapping_is_readonly_and_isolated(self):
        values = {"win_10m_count": 3.0}
        feat = FeatureSnapshot(feature_set_version="f1", as_of_time="t", values=values)
        values["win_10m_count"] = 999.0  # mutate original dict
        self.assertEqual(feat.values["win_10m_count"], 3.0)
        self.assertIsInstance(feat.values, MappingProxyType)
        with self.assertRaises(TypeError):
            feat.values["x"] = 1.0  # read-only view

    def test_allowed_lists_frozen(self):
        auth = AuthorizationSnapshot(
            authority_source="src", snapshot_id="s1", subject_id="u1",
            data_domain="d1", result=AuthorizationResult.AUTHORIZED,
            allowed_recipients=["rcpt1"],
        )
        self.assertEqual(auth.allowed_recipients, ("rcpt1",))
        self.assertIsInstance(auth.allowed_recipients, tuple)


if __name__ == "__main__":
    unittest.main()
