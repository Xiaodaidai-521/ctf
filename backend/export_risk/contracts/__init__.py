"""Public contract surface for export_risk (frozen dataclasses, no Django).

Import contracts from here (``from export_risk.contracts import ...``) rather
than reaching into submodules, so the internal layout can change without
breaking consumers.
"""

from .assessment import ExportRiskAssessment, Obligation
from .enums import (
    AuthorizationResult,
    Disposition,
    QualityState,
    RecommendedAction,
    RiskLevel,
    SourceMode,
)
from .execution import ExecutionAuthorization, NotExecutable
from .freezing import deep_freeze
from .snapshots import (
    AuthorizationSnapshot,
    BehaviorBaseline,
    ExportRequestSnapshot,
    FeatureSnapshot,
    SensitivityProfileRef,
)

__all__ = [
    "ExportRiskAssessment",
    "Obligation",
    "ExecutionAuthorization",
    "NotExecutable",
    "AuthorizationResult",
    "Disposition",
    "QualityState",
    "RecommendedAction",
    "RiskLevel",
    "SourceMode",
    "deep_freeze",
    "AuthorizationSnapshot",
    "BehaviorBaseline",
    "ExportRequestSnapshot",
    "FeatureSnapshot",
    "SensitivityProfileRef",
]
