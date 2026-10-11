"""Pure fusion layer (regex spec E8, I4; review R4).

One engine for all four arms. The base-protection floor is applied for **every**
arm (non-ablatable); only the policy flags/thresholds differ, so differences are
attributable to the fusion configuration. Produces an action, obligations,
reason codes, an anomaly component and a risk level. Pure: no clock/DB/settings.
"""

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from ..contracts import (
    ExportRequestSnapshot,
    Obligation,
    RecommendedAction,
    RiskLevel,
    SensitivityProfileRef,
)
from ..contracts import reason_codes as rc
from ..policies.catalog import Policy, base_protection_obligations
from .anomaly import anomaly_signal

_SEVERITY = {
    RecommendedAction.ALLOW: 0,
    RecommendedAction.MASK: 1,
    RecommendedAction.DEFER: 2,
    RecommendedAction.REQUIRE_APPROVAL: 2,
    RecommendedAction.DENY: 3,
}


def _escalate(current: RecommendedAction, candidate: RecommendedAction) -> RecommendedAction:
    return candidate if _SEVERITY[candidate] > _SEVERITY[current] else current


@dataclass(frozen=True)
class FusionResult:
    action: RecommendedAction
    risk_level: RiskLevel
    reason_codes: Sequence[str] = field(default_factory=tuple)
    obligations: Sequence[Obligation] = field(default_factory=tuple)
    anomaly_component: Optional[Mapping[str, object]] = None
    risk_score: Optional[float] = None


def fuse(policy: Policy, request: ExportRequestSnapshot, profile: SensitivityProfileRef,
         values: Mapping[str, object]) -> FusionResult:
    """Combine base protection + arm-specific signals into an action."""
    reasons = [rc.BASELINE_WITHIN_AUTHORIZED]
    obligations = []
    action = RecommendedAction.ALLOW
    anomaly_high = False
    score = None

    # Base-protection floor — all arms, cannot be ablated (review R4).
    base = base_protection_obligations(profile.protection_level, profile.categories)
    if base:
        obligations.extend(base)
        action = _escalate(action, RecommendedAction.MASK)
        reasons.append(rc.FUSION_BASE_PROTECTION)

    # Arm A: single-request quantity threshold.
    if policy.single_request_threshold is not None and request.record_count > policy.single_request_threshold:
        action = _escalate(action, RecommendedAction.REQUIRE_APPROVAL)
        reasons.append(rc.FUSION_SINGLE_THRESHOLD)

    # Arm B / D: multi-window cumulative thresholds.
    if policy.use_cumulative:
        for feat, thr in policy.cumulative_thresholds.items():
            v = values.get(feat)
            if v is not None and float(v) > float(thr):
                action = _escalate(action, RecommendedAction.REQUIRE_APPROVAL)
                reasons.append(rc.FUSION_CUMULATIVE_EXCEEDED)
                break

    # Arm C / D: anomaly signal.
    anomaly_component = None
    if policy.use_anomaly:
        score, method, model_available = anomaly_signal(values)
        anomaly_component = {
            "score": score, "method": method,
            "model_available": model_available, "threshold": policy.anomaly_threshold,
        }
        if score is None:
            reasons.append(rc.FUSION_ANOMALY_MODEL_UNAVAILABLE)  # not silently cleared (I6)
        elif score > policy.anomaly_threshold:
            action = _escalate(action, RecommendedAction.REQUIRE_APPROVAL)
            anomaly_high = True
            reasons.append(rc.FUSION_ANOMALY_HIGH)

    # Arm D: high sensitivity combined with an anomaly → stronger obligation.
    if policy.use_sensitivity and profile.protection_level in {"high", "critical"} and anomaly_high:
        action = _escalate(action, RecommendedAction.REQUIRE_APPROVAL)
        reasons.append(rc.FUSION_SENSITIVE_ANOMALY)
        obligations.append(Obligation(
            obligation_id="d.sensitive_approval", type="approval",
            parameters={"reason": "high_sensitivity_with_anomaly"},
            applicable_scope="request", enforcement_stage="pre_decision",
            required_evidence=("approver_id",),
        ))

    level = _finalize_level(action, anomaly_high)
    # De-duplicate reasons preserving order.
    seen, ordered = set(), []
    for code in reasons:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return FusionResult(action, level, tuple(ordered), tuple(obligations), anomaly_component, score)


def _finalize_level(action: RecommendedAction, anomaly_high: bool) -> RiskLevel:
    if anomaly_high:
        return RiskLevel.HIGH
    if _SEVERITY[action] >= _SEVERITY[RecommendedAction.REQUIRE_APPROVAL]:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
