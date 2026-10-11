"""Pure structured explanation (regex spec C2): three separated parts.

1. observed      — raw feature values (what happened)
2. model_described — how the anomaly layer described it (score + method)
3. policy_driven — which policy/version and reasons drove the action

Generated from structured evidence only; never fabricates a model contribution
from a plain feature deviation when no attribution method exists.
"""

from typing import Mapping, Optional, Sequence


def build_explanation(
    values: Mapping[str, object],
    anomaly_component: Optional[Mapping[str, object]],
    policy_version: str,
    arm: str,
    reason_codes: Sequence[str],
) -> Mapping[str, object]:
    observed = {k: v for k, v in values.items() if not k.startswith("dev::") and not k.startswith("anomaly::")}
    deviations = {k: v for k, v in values.items() if k.startswith("dev::")}
    model_described = dict(anomaly_component) if anomaly_component else {"method": "none", "score": None}
    return {
        "observed": observed,
        "deviations": deviations,
        "model_described": model_described,
        "policy_driven": {"policy_version": policy_version, "arm": arm, "reasons": list(reason_codes)},
    }
