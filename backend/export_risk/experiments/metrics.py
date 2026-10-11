"""Metrics over a replay (regex spec I6).

Denominators are explicit and failures are never dropped: the false-intercept
rate is over labelled-normal steps and is None (reported, not hidden) when there
are no normal steps. All metrics are over simulated ledgers (``simulated``).
"""

from dataclasses import dataclass, field
from typing import Mapping, Optional

INF = float("inf")


@dataclass(frozen=True)
class ArmMetrics:
    arm: str
    policy: str
    total_steps: int
    normal_steps: int
    action_distribution: Mapping[str, int] = field(default_factory=dict)
    false_intercept_rate: Optional[float] = None
    first_restriction_index: Optional[int] = None  # None = never restricted (censored)
    simulated: bool = True


def arm_metrics(arm: str, replay) -> ArmMetrics:
    dist = {}
    normal = 0
    false_intercept = 0
    for o in replay.outcomes:
        dist[o.action] = dist.get(o.action, 0) + 1
        if o.label == "normal":
            normal += 1
            if o.restricted:
                false_intercept += 1
    rate = (false_intercept / normal) if normal else None
    return ArmMetrics(
        arm=arm, policy=replay.arm_policy, total_steps=len(replay.outcomes),
        normal_steps=normal, action_distribution=dist, false_intercept_rate=rate,
        first_restriction_index=replay.first_restriction_index,
    )


def first_restriction_or_inf(metrics: ArmMetrics) -> float:
    """Censored first-restriction position: inf when the arm never restricts."""
    return INF if metrics.first_restriction_index is None else float(metrics.first_restriction_index)
