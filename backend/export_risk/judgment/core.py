"""Deterministic judgment core: assess_risk (regex spec E1/E2, H5).

Pure function. It reads only its explicit arguments and returns an
ExportRiskAssessment. It does **not** read the clock, DB, settings or quota, and
it never writes state or signs an authorization. `evaluation_time` is injected
so authorization validity and replay are reproducible without reading a clock.

Consistency -> hard constraints -> authorization/profile/input degradation ->
policy fusion. A missing trained anomaly model is explicitly disclosed; the
available fallback is a robust-deviation aggregate, not a learned model.
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
    SourceMode,
)
from ..contracts import reason_codes as rc
from ..policies import resolve_policy
from .consistency import check_consistency
from .explanation import build_explanation
from .fusion import fuse
from .hard_constraints import evaluate_hard_constraints
from .validity import authorization_validity

_M0_UNCERTAINTY = (
    "arm C trained anomaly model unavailable (scikit-learn not installed); "
    "anomaly falls back to robust-deviation aggregate"
)


def _weakest_source_mode(*modes: SourceMode) -> SourceMode:
    """Least-trusted provenance among inputs (pure): production iff all are.

    So the decision layer can refuse a production signing whose assessment was
    fed any synthetic/evaluation input — including the sensitivity profile, which
    the decision/prepare layers never see directly.
    """
    if any(m == SourceMode.SYNTHETIC for m in modes):
        return SourceMode.SYNTHETIC
    if any(m == SourceMode.EVALUATION for m in modes):
        return SourceMode.EVALUATION
    return SourceMode.PRODUCTION


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

    # Provenance of the whole input set: a production signing path must refuse a
    # decision whose assessment consumed any synthetic/evaluation input (the
    # sensitivity profile included), so carry the weakest source mode forward.
    effective_source = _weakest_source_mode(
        request_snapshot.source_mode,
        authorization_snapshot.source_mode,
        sensitivity_profile.source_mode,
    )

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
            input_source_mode=effective_source,
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

    # 2.5) An AUTHORIZED authorization must still be temporally valid at the
    #      injected evaluation_time (review F2). Expired / unknown-validity is a
    #      degrade (defer), never silently treated as valid-forever.
    if authorization_snapshot.result == AuthorizationResult.AUTHORIZED:
        validity_code = authorization_validity(authorization_snapshot, evaluation_time)
        if validity_code is not None:
            return build(RecommendedAction.DEFER, RiskLevel.UNKNOWN, (validity_code,), QualityState.MISSING)

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

    # 5) Missing feature data is not an observed zero (review F13/R5). A
    #    cumulative arm needs each of its input features actually observed: a
    #    required feature that is absent or flagged in `missing` degrades to
    #    defer, not a silent zero — this covers both a wholly absent snapshot and
    #    a present-but-partial one. Anomaly-only arms defer only when there is no
    #    snapshot at all (a present snapshot's unavailable model is disclosed by
    #    the fusion layer, not silently cleared).
    policy = resolve_policy(policy_version)
    values = dict(feature_snapshot.values) if feature_snapshot else {}
    missing = set(feature_snapshot.missing) if feature_snapshot else set()
    if policy.use_cumulative:
        unavailable = [f for f in policy.cumulative_thresholds if f in missing or f not in values]
        if unavailable:
            return build(
                RecommendedAction.DEFER, RiskLevel.UNKNOWN, (rc.DEGRADE_FEATURES_MISSING,),
                QualityState.MISSING,
            )
    elif feature_snapshot is None and policy.use_anomaly:
        return build(
            RecommendedAction.DEFER, RiskLevel.UNKNOWN, (rc.DEGRADE_FEATURES_MISSING,),
            QualityState.MISSING,
        )

    # 6) Authorized, within envelope, profile and policy evidence present -> fusion.
    result = fuse(policy, request_snapshot, sensitivity_profile, values)
    explanation = build_explanation(
        values, result.anomaly_component, policy.version, policy.arm, result.reason_codes
    )
    # Preserve the real input quality (review F13): never relabel STALE/degraded
    # feature inputs as OK. Baseline-only policies may legitimately have no snapshot.
    input_quality = feature_snapshot.quality if feature_snapshot else QualityState.OK
    return build(
        result.action, result.risk_level, result.reason_codes, input_quality,
        obligations=result.obligations, anomaly_component=result.anomaly_component,
        explanation=explanation, risk_score=result.risk_score,
    )
