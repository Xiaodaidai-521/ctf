"""Feature registry and pure windowed computation (input-prep layer)."""

from .compute import (
    DeliveryRec,
    EventRecord,
    build_feature_snapshot,
    compute_behavior_features,
    compute_delivery_features,
)
from .registry import FEATURE_REGISTRY, FeatureDefinition

__all__ = [
    "FEATURE_REGISTRY",
    "FeatureDefinition",
    "EventRecord",
    "DeliveryRec",
    "build_feature_snapshot",
    "compute_behavior_features",
    "compute_delivery_features",
]
