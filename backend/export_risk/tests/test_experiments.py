"""M5: experiment harness — scenarios, replay, four-arm comparison, hypotheses."""

import unittest

from export_risk.experiments import (
    all_scenarios,
    check_hypotheses,
    continuous_batch,
    new_account,
    run_comparison,
    unapproved_recipient,
)


class ExperimentHarnessTests(unittest.TestCase):
    def test_harness_runs_and_is_marked_simulated(self):
        report = check_hypotheses(all_scenarios())
        self.assertTrue(report["simulated"])
        self.assertIn("continuous_batch", report["by_scenario"])

    def test_h1_cumulative_arm_restricts_before_single_threshold(self):
        report = check_hypotheses([continuous_batch(), ])
        h1 = report["hypotheses"]["H1_B_restricts_before_A"]
        self.assertIsNotNone(h1["B_first"])     # B does restrict
        self.assertIsNone(h1["A_first"])        # A never restricts (censored)
        self.assertTrue(h1["holds"])

    def test_hard_deny_is_common_to_every_arm(self):
        # Review R4 / invariant: the hard-constraint layer is identical across arms.
        comparison = run_comparison(unapproved_recipient())
        for arm, metrics in comparison.items():
            self.assertEqual(metrics.action_distribution.get("deny"), 1, f"arm {arm} did not deny")

    def test_action_distribution_denominator_is_complete(self):
        comparison = run_comparison(continuous_batch())
        for metrics in comparison.values():
            self.assertEqual(sum(metrics.action_distribution.values()), metrics.total_steps)

    def test_new_account_cold_start_not_falsely_restricted(self):
        comparison = run_comparison(new_account())
        for arm, metrics in comparison.items():
            self.assertIsNone(metrics.first_restriction_index, f"arm {arm} restricted a cold-start normal op")


if __name__ == "__main__":
    unittest.main()
