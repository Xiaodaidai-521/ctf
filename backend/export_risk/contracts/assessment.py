"""Output contracts produced by the judgment core (regex spec H3).

`ExportRiskAssessment` is **named distinctly** from
`legal.services.risk_evaluator.RiskAssessment`, which is an unrelated
keyword-scoring dataclass (Stage-1 finding F2). Frozen, no Django dependency.
"""

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from .enums import QualityState, RecommendedAction, RiskLevel
from .freezing import freeze_field


@dataclass(frozen=True)
class Obligation:
    """A duty the downstream executor must honour before/at delivery (H3).

    If an executor cannot honour an obligation, the decision layer must not sign
    an authorization carrying it (invariant: unsupported obligation -> no auth).
    """

    obligation_id: str
    type: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    applicable_scope: str = ""
    enforcement_stage: str = ""
    required_evidence: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        freeze_field(self, "parameters")
        freeze_field(self, "required_evidence")


@dataclass(frozen=True)
class ExportRiskAssessment:
    """Result of the pure judgment core (H3).

    It references its inputs by id/version so every decision is traceable to the
    exact request, profile, features, model and policy that produced it. The core
    returns this object only; it never writes state or signs an authorization.
    """

    request_id: str
    request_fingerprint: str
    recommended_action: RecommendedAction
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    hard_constraint_triggered: bool = False
    reason_codes: Sequence[str] = field(default_factory=tuple)
    obligations: Sequence[Obligation] = field(default_factory=tuple)
    evidence_refs: Sequence[str] = field(default_factory=tuple)
    sensitivity_summary: Mapping[str, object] = field(default_factory=dict)
    anomaly_component: Optional[Mapping[str, object]] = None
    explanation: Mapping[str, object] = field(default_factory=dict)
    risk_score: Optional[float] = None
    risk_score_meaning: str = ""
    input_quality: QualityState = QualityState.OK
    uncertainty: str = ""
    authorization_snapshot_id: str = ""
    profile_id: str = ""
    feature_set_version: str = ""
    model_version: str = ""
    policy_version: str = ""
    schema_version: str = "m0"

    def __post_init__(self) -> None:
        for name in ("reason_codes", "obligations", "evidence_refs", "sensitivity_summary"):
            freeze_field(self, name)
        freeze_field(self, "explanation")
        if self.anomaly_component is not None:
            freeze_field(self, "anomaly_component")
