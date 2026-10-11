"""Input adapters (behaviour sources, provider protocol)."""

from .behavior import BehaviorProvider, DjangoBehaviorProvider, SyntheticBehaviorProvider

__all__ = ["BehaviorProvider", "DjangoBehaviorProvider", "SyntheticBehaviorProvider"]
