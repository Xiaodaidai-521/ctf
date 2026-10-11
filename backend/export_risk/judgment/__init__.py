"""Deterministic judgment core (pure, no Django).

Everything under judgment/ is side-effect free: no clock, DB, settings, network
or unseeded randomness. This is enforced by the AST purity test. Import the
entry point from here: ``from export_risk.judgment import assess_risk``.
"""

from .consistency import check_consistency
from .core import assess_risk
from .fusion import FusionResult, fuse
from .hard_constraints import HardConstraintOutcome, evaluate_hard_constraints

__all__ = [
    "assess_risk",
    "check_consistency",
    "evaluate_hard_constraints",
    "HardConstraintOutcome",
    "fuse",
    "FusionResult",
]
