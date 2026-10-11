"""Deterministic judgment core: assess_risk (regex spec E1/E2, H5).

Pure function. It reads only its explicit arguments and returns an
ExportRiskAssessment. It does **not** read the clock, DB, settings or quota, and
it never writes state or signs an authorization. `evaluation_time` is injected
so replay is reproducible (review R7); M0 carries it without reading a clock.

M0 scope: consistency -> hard constraints -> degrade handling -> baseline allow.
Behavioural features, baselines, anomaly scoring and sensitivity/business fusion
are not yet applied; this is surfaced in `uncertainty`, so an ALLOW here means
"not over-authorized and inputs consistent", not "behaviourally cleared".
"""

from typing import Optional

from ..contracts import (
    AuthorizationResult,
    AuthorizationSnapshot,
    ExportRequestSnapshot,
    ExportRiskAssessment,
    FeatureSnapshot,
    QualityState,
    RecommendedAction,
    RiskLevel,
    SensitivityProfileRef,
)
from ..contracts import reason_codes as rc
from ..policies import resolve_policy
from .consistency import check_consistency
from .explanation import build_explanation
from .fusion import fuse
from .hard_constraints import evaluate_hard_constraints

_M0_UNCERTAINTY = (
    "arm C trained anomaly model unavailable (scikit-learn not installed); "
    "anomaly falls back to robust-deviation aggregate"
)


def assess_risk(
    request_snapshot: ExportRequestSnapshot,
    sensitivity_profile: SensitivityProfileRef,
    authorization_snapshot: AuthorizationSnapshot,
    feature_snapshot: Optional[FeatureSnapshot],
    model_version: str,
    policy_version: str,
    evaluation_time: str,
) -> ExportRiskAssessment:
    """Return a risk assessment from explicit inputs only."""

    def build(action, level, codes, quality, obligations=(), anomaly_component=None,
              explanation=None, risk_score=None):
        return ExportRiskAssessment(
            request_id=request_snapshot.request_id,
            request_fingerprint=request_snapshot.request_fingerprint,
            recommended_action=action,
            risk_level=level,
            hard_constraint_triggered=(action == RecommendedAction.DENY),
            reason_codes=tuple(codes),
            obligations=tuple(obligations),
            anomaly_component=anomaly_component,
            explanation=explanation or {},
            risk_score=risk_score,
            input_quality=quality,
            uncertainty=_M0_UNCERTAINTY,
            authorization_snapshot_id=authorization_snapshot.snapshot_id,
            profile_id=sensitivity_profile.profile_id,
            feature_set_version=(feature_snapshot.feature_set_version if feature_snapshot else ""),
            model_version=model_version,
            policy_version=policy_version,
        )

    # 1) Cross-input consistency: inconsistent inputs must not be fused into an
    #    allow. Defer on mismatch (safe side), never deny for lack of agreement.
    consistency_codes = check_consistency(request_snapshot, sensitivity_profile, authorization_snapshot)
    if consistency_codes:
        return build(RecommendedAction.DEFER, RiskLevel.UNKNOWN, consistency_codes, QualityState.STALE)

    # 2) Hard constraints: explicit over-authorization -> deny, no model needed.
    hard = evaluate_hard_constraints(request_snapshot, authorization_snapshot)
    if hard.triggered:
        return build(RecommendedAction.DENY, RiskLevel.HIGH, hard.reason_codes, QualityState.OK)

    # 3) Unknown authorization is never silently allowed (invariant D4).
    if authorization_snapshot.result != AuthorizationResult.AUTHORIZED:
        return build(
            RecommendedAction.DEFER, RiskLevel.UNKNOWN,
            (rc.DEGRADE_AUTHORIZATION_UNKNOWN,), QualityState.MISSING,
        )

    # 4) Incomplete sensitivity profile is not "not sensitive": require approval.
    if sensitivity_profile.coverage != QualityState.OK or sensitivity_profile.status == "unknown":
        return build(
            RecommendedAction.REQUIRE_APPROVAL, RiskLevel.MEDIUM,
            (rc.DEGRADE_PROFILE_INCOMPLETE,), QualityState.PROFILE_INCOMPLETE,
        )

    # 5) Authorized, within envelope, consistent, profile present -> fusion layer
    #    (base-protection floor + arm-specific cumulative/anomaly/sensitivity).
    policy = resolve_policy(policy_version)
    values = dict(feature_snapshot.values) if feature_snapshot else {}
    result = fuse(policy, request_snapshot, sensitivity_profile, values)
    explanation = build_explanation(
        values, result.anomaly_component, policy.version, policy.arm, result.reason_codes
    )
    return build(
        result.action, result.risk_level, result.reason_codes, QualityState.OK,
        obligations=result.obligations, anomaly_component=result.anomaly_component,
        explanation=explanation, risk_score=result.risk_score,
    )
