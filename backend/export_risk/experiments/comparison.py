"""Four-arm comparison and pre-registered hypothesis checks (regex spec I4/I7).

Arms share one engine and the identical hard-constraint + base-protection
layers; only the fusion policy differs. Hypotheses are registered up front (R4):
they are checked and reported whether or not they hold — never redefined after
seeing results. All results are over synthetic, simulated data.
"""

from .metrics import arm_metrics, first_restriction_or_inf
from .replay import replay_arm

ARMS = {"A": "A-v1", "B": "B-v1", "C": "C-v1", "D": "D-v1"}


def run_comparison(scenario, arms=ARMS):
    """Return {arm: ArmMetrics} for one scenario across all arms."""
    return {arm: arm_metrics(arm, replay_arm(scenario, policy)) for arm, policy in arms.items()}


def check_hypotheses(scenarios):
    """Evaluate registered hypotheses H1/H2 over the given scenarios."""
    by_name = {s.name: run_comparison(s) for s in scenarios}
    hyp = {}

    # H1: on continuous batching, cumulative arm B restricts earlier than the
    # single-threshold arm A (A is expected to never restrict -> censored = inf).
    cb = by_name.get("continuous_batch")
    if cb:
        hyp["H1_B_restricts_before_A"] = {
            "B_first": cb["B"].first_restriction_index,
            "A_first": cb["A"].first_restriction_index,
            "holds": first_restriction_or_inf(cb["B"]) < first_restriction_or_inf(cb["A"]),
        }

    # H2: on normal bulk, D's false-intercept rate is not worse than C's
    # (descriptive comparison on synthetic data; not a powered statistical claim).
    nb = by_name.get("normal_bulk")
    if nb:
        c_rate = nb["C"].false_intercept_rate or 0.0
        d_rate = nb["D"].false_intercept_rate or 0.0
        hyp["H2_D_not_worse_than_C"] = {"C": c_rate, "D": d_rate, "holds": d_rate <= c_rate}

    return {"by_scenario": by_name, "hypotheses": hyp, "simulated": True}
