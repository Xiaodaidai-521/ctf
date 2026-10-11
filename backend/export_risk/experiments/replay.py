"""Stateful single-arm replay (regex spec I5).

Replays a scenario under one policy with virtual time: at each step only events
observed up to that step's ``as_of`` are visible, deviations are computed against
a replay-safe baseline, and the pure judgment core is called. State carried
forward is the accumulated event history (a disclosed closed-loop assumption:
each arm maintains its own simulated state). All outcomes are simulated.
"""

from dataclasses import dataclass, field, replace
from typing import Optional, Sequence

from ..baselines import build_baseline, compute_deviations
from ..contracts import RecommendedAction
from ..features import build_feature_snapshot
from ..judgment import assess_risk

RESTRICTIVE = {RecommendedAction.DENY, RecommendedAction.REQUIRE_APPROVAL, RecommendedAction.DEFER}


@dataclass(frozen=True)
class StepOutcome:
    step_index: int
    action: str
    reason_codes: Sequence[str]
    restricted: bool
    label: str


@dataclass(frozen=True)
class ArmReplay:
    arm_policy: str
    outcomes: Sequence[StepOutcome] = field(default_factory=tuple)
    first_restriction_index: Optional[int] = None
    simulated: bool = True


def replay_arm(scenario, policy_version: str, model_version: str = "exp-model") -> ArmReplay:
    history = []
    outcomes = []
    first_restrict = None
    for idx, step in enumerate(scenario.steps):
        history = history + list(step.new_events)  # known at this virtual time
        snap = build_feature_snapshot(history, [], step.as_of, step.as_of, feature_set_version="exp-fs")
        values = dict(snap.values)
        if scenario.baseline_observations:
            bundle = build_baseline(
                scenario.baseline_observations, subject_id=scenario.subject_id,
                cohort_key=scenario.cohort_key, cutoff=step.as_of, feature_names=("req_count_long",),
            )
            for key, dev in compute_deviations(bundle, {"req_count_long": values.get("req_count_long", 0.0)}).items():
                if dev is not None:
                    values["dev::" + key] = dev
        snap2 = replace(snap, values=values)
        assessment = assess_risk(step.request, step.profile, step.authorization, snap2,
                                 model_version, policy_version, step.as_of.isoformat())
        restricted = assessment.recommended_action in RESTRICTIVE
        if restricted and first_restrict is None:
            first_restrict = idx
        outcomes.append(StepOutcome(idx, assessment.recommended_action.value,
                                    tuple(assessment.reason_codes), restricted, step.label))
    return ArmReplay(policy_version, tuple(outcomes), first_restrict)
