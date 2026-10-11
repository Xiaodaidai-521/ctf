"""Experiment harness: scenarios, stateful replay, metrics, four-arm comparison.

Test-support only — not part of the production request chain (regex spec D1.8).
"""

from .comparison import ARMS, check_hypotheses, run_comparison
from .metrics import ArmMetrics, arm_metrics, first_restriction_or_inf
from .replay import ArmReplay, StepOutcome, replay_arm
from .scenarios import all_scenarios, continuous_batch, new_account, normal_bulk, unapproved_recipient

__all__ = [
    "ARMS",
    "check_hypotheses",
    "run_comparison",
    "ArmMetrics",
    "arm_metrics",
    "first_restriction_or_inf",
    "ArmReplay",
    "StepOutcome",
    "replay_arm",
    "all_scenarios",
    "continuous_batch",
    "new_account",
    "normal_bulk",
    "unapproved_recipient",
]
