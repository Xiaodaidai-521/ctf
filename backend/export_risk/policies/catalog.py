"""Versioned policy catalog for the four comparison arms (regex spec E8, I4).

One engine, four **data** policies; the hard-constraint and base-protection
layers are identical across arms (enforced in the engine, not here), so only the
fusion layer varies and improvements are attributable. Policies are closed data
(thresholds + flags), never executable rules (regex spec M: no eval). Content is
hash-addressed so a decision pins the exact policy that produced it.
"""

from dataclasses import dataclass, field
from typing import Mapping, Optional
import hashlib
import json

from ..contracts import Obligation


# Base-protection floor (review R4): applied to EVERY arm regardless of policy,
# so it can never be ablated away. Mask protected categories before delivery.
def base_protection_obligations(protection_level: str, categories) -> tuple:
    if categories:
        return (
            Obligation(
                obligation_id="base.mask_protected",
                type="mask",
                parameters={"categories": tuple(categories), "level": protection_level},
                applicable_scope="protected_fields",
                enforcement_stage="pre_delivery",
                required_evidence=("mask_report",),
            ),
        )
    return tuple()


@dataclass(frozen=True)
class Policy:
    """A versioned fusion policy for one comparison arm."""

    version: str
    arm: str
    label: str = ""
    single_request_threshold: Optional[int] = None   # arm A
    use_cumulative: bool = False                      # arm B, D
    cumulative_thresholds: Mapping[str, float] = field(default_factory=dict)
    use_anomaly: bool = False                         # arm C, D
    anomaly_threshold: float = 3.0
    use_sensitivity: bool = False                     # arm D

    def __post_init__(self):
        from ..contracts.freezing import freeze_field
        freeze_field(self, "cumulative_thresholds")


def policy_hash(policy: Policy) -> str:
    """Deterministic content hash of a policy (pins it to a decision)."""
    payload = {
        "version": policy.version, "arm": policy.arm,
        "single_request_threshold": policy.single_request_threshold,
        "use_cumulative": policy.use_cumulative,
        "cumulative_thresholds": dict(policy.cumulative_thresholds),
        "use_anomaly": policy.use_anomaly, "anomaly_threshold": policy.anomaly_threshold,
        "use_sensitivity": policy.use_sensitivity,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# DRAFT thresholds — not approved parameters (regex spec E8 / review R5).
POLICIES = {
    "policy-m0": Policy(version="policy-m0", arm="A", label="M0 pass-through baseline"),
    "A-v1": Policy(version="A-v1", arm="A", label="single-request quantity threshold",
                   single_request_threshold=1000),
    "B-v1": Policy(version="B-v1", arm="B", label="multi-window cumulative", use_cumulative=True,
                   cumulative_thresholds={"req_count_long": 50.0, "distinct_objects_long": 200.0}),
    "C-v1": Policy(version="C-v1", arm="C", label="behavioural anomaly model", use_anomaly=True,
                   anomaly_threshold=3.0),
    "D-v1": Policy(version="D-v1", arm="D", label="sensitivity + behaviour + business",
                   use_cumulative=True,
                   cumulative_thresholds={"req_count_long": 50.0, "distinct_objects_long": 200.0},
                   use_anomaly=True, anomaly_threshold=3.0, use_sensitivity=True),
}


def resolve_policy(version: str) -> Policy:
    """Return the pinned policy for ``version``; raise on unknown (no latest)."""
    try:
        return POLICIES[version]
    except KeyError:
        raise KeyError(f"unknown policy version: {version!r}") from None
