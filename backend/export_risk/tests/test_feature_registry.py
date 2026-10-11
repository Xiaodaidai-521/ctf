"""M1: feature registry completeness and fingerprint (E4)."""

import unittest

from export_risk.features import FEATURE_REGISTRY
from export_risk.features.registry import registry_fingerprint


class FeatureRegistryTests(unittest.TestCase):
    def test_all_features_have_complete_metadata(self):
        gaps = {f.name: f.metadata_gaps() for f in FEATURE_REGISTRY if f.metadata_gaps()}
        self.assertEqual(gaps, {}, f"features missing E4 metadata: {gaps}")

    def test_feature_names_unique(self):
        names = [f.name for f in FEATURE_REGISTRY]
        self.assertEqual(len(names), len(set(names)))

    def test_history_features_exclude_current_request(self):
        # Invariant E4: the current request must not be pre-folded into history.
        for f in FEATURE_REGISTRY:
            self.assertFalse(f.counts_current_request, f"{f.name} counts current request")

    def test_fingerprint_is_deterministic_and_order_independent(self):
        fp1 = registry_fingerprint(FEATURE_REGISTRY)
        fp2 = registry_fingerprint(tuple(reversed(FEATURE_REGISTRY)))
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)

    def test_fingerprint_changes_when_metadata_changes(self):
        from dataclasses import replace
        base = registry_fingerprint(FEATURE_REGISTRY)
        mutated = (replace(FEATURE_REGISTRY[0], window_seconds=1),) + FEATURE_REGISTRY[1:]
        self.assertNotEqual(base, registry_fingerprint(mutated))


if __name__ == "__main__":
    unittest.main()
