"""Baseline construction and robust deviation (input-prep layer)."""

from .baseline import (
    BaselineBundle,
    BaselineStats,
    Observation,
    build_baseline,
    compute_deviations,
)

__all__ = [
    "BaselineBundle",
    "BaselineStats",
    "Observation",
    "build_baseline",
    "compute_deviations",
]
