"""Closed enumerations for the judgment contracts.

All values are plain strings so snapshots stay JSON-serialisable without pulling
in Django. These enums are the *only* legal values for the matching fields; the
judgment core must never invent an action or disposition outside these sets.
"""

from enum import Enum


class RecommendedAction(str, Enum):
    """Action proposed by the judgment core (regex spec H3)."""

    ALLOW = "allow"
    MASK = "mask"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"
    DEFER = "defer"


class Disposition(str, Enum):
    """Non-executable disposition surfaced by the decision layer (H4)."""

    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    DEFER = "defer"


class AuthorizationResult(str, Enum):
    """Outcome of an authorization snapshot lookup.

    `UNKNOWN` is never silently treated as allowed (invariant D4).
    """

    AUTHORIZED = "authorized"
    FORBIDDEN = "forbidden"
    UNKNOWN = "unknown"


class SourceMode(str, Enum):
    """Provenance of an input snapshot (review R3 admission contract).

    A production signing path must accept PRODUCTION only; SYNTHETIC/EVALUATION
    inputs must never obtain a production authorization. This flag is set by the
    trusted assembly layer, never trusted from a client payload.
    """

    PRODUCTION = "production"
    EVALUATION = "evaluation"
    SYNTHETIC = "synthetic"


class RiskLevel(str, Enum):
    """Coarse risk band. UNKNOWN when inputs are insufficient to rank."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class QualityState(str, Enum):
    """Input-quality marker carried into the assessment (regex spec E/H2)."""

    OK = "ok"
    MISSING = "missing"
    STALE = "stale"
    INSUFFICIENT_HISTORY = "insufficient_history"
    PROFILE_INCOMPLETE = "profile_incomplete"
