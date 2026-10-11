"""M2: baselines, cold-start fallback, replay safety (E6)."""

import unittest
from datetime import datetime, timedelta, timezone

from export_risk.baselines import Observation, build_baseline, compute_deviations
from export_risk.baselines import statistics as st

CUTOFF = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)
FEATS = ("req_count_long",)


def obs(subject, cohort, days_ago, value):
    return Observation(subject_id=subject, cohort_key=cohort,
                       as_of=CUTOFF - timedelta(days=days_ago), values={"req_count_long": value})


class StatisticsTests(unittest.TestCase):
    def test_percentile_linear_interpolation(self):
        xs = [1, 2, 3, 4]
        self.assertEqual(st.median(xs), 2.5)
        self.assertAlmostEqual(st.percentile(xs, 25.0), 1.75)

    def test_robust_deviation_degenerate_spread(self):
        self.assertEqual(st.robust_deviation(5, 5, 0), 0.0)
        self.assertIsNone(st.robust_deviation(9, 5, 0))  # cannot rank, not zero/inf


class BaselineTests(unittest.TestCase):
    def test_subject_baseline_when_enough_history(self):
        data = [obs("u1", "cohortA", d, v) for d, v in enumerate([3, 4, 5, 4, 3, 4], start=1)]
        b = build_baseline(data, subject_id="u1", cohort_key="cohortA", cutoff=CUTOFF, feature_names=FEATS)
        self.assertEqual(b.baseline.scope, "subject")
        self.assertTrue(b.usable)
        self.assertAlmostEqual(b.stats["req_count_long"].median, 4.0)

    def test_cold_start_falls_back_to_cohort(self):
        data = [obs("u1", "cohortA", 1, 10)]  # only 1 own sample (< min_subject)
        data += [obs(f"peer{i}", "cohortA", i % 5 + 1, 4) for i in range(25)]  # cohort has enough
        b = build_baseline(data, subject_id="u1", cohort_key="cohortA", cutoff=CUTOFF, feature_names=FEATS)
        self.assertEqual(b.baseline.scope, "cohort")
        self.assertTrue(b.usable)

    def test_no_history_is_not_normal(self):
        b = build_baseline([], subject_id="u1", cohort_key="cohortA", cutoff=CUTOFF, feature_names=FEATS)
        self.assertFalse(b.usable)
        self.assertEqual(b.stats, {})
        self.assertEqual(compute_deviations(b, {"req_count_long": 999.0}), {})  # no fabricated deviation

    def test_replay_excludes_future_samples(self):
        data = [obs("u1", "cohortA", d, 4) for d in range(1, 7)]      # all before cutoff
        future = [Observation("u1", "cohortA", CUTOFF + timedelta(days=1), {"req_count_long": 1000.0})]
        b = build_baseline(data + future, subject_id="u1", cohort_key="cohortA",
                           cutoff=CUTOFF, feature_names=FEATS)
        self.assertEqual(b.stats["req_count_long"].sample_count, 6)   # future sample ignored
        self.assertAlmostEqual(b.stats["req_count_long"].median, 4.0)

    def test_deviation_against_subject_baseline(self):
        data = [obs("u1", "cohortA", d, v) for d, v in enumerate([2, 3, 4, 3, 2, 3], start=1)]
        b = build_baseline(data, subject_id="u1", cohort_key="cohortA", cutoff=CUTOFF, feature_names=FEATS)
        dev = compute_deviations(b, {"req_count_long": 20.0})
        self.assertIsNotNone(dev["req_count_long"])
        self.assertGreater(dev["req_count_long"], 0)  # far above own history


if __name__ == "__main__":
    unittest.main()
