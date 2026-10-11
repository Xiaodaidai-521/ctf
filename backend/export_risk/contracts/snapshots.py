"""Input snapshots for the judgment core (regex spec H2).

All snapshots are frozen dataclasses with **no Django dependency**. Nested
collections are deep-frozen in __post_init__ (review R7) so a snapshot is
value-stable once built. Times are carried as explicit ISO strings supplied by
the caller; the judgment core never reads the clock itself.
"""

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from .enums import AuthorizationResult, QualityState, SourceMode
from .freezing import freeze_field


@dataclass(frozen=True)
class ExportRequestSnapshot:
    """A single export/share attempt, as built server-side.

    `scope` is the set of object identifiers (and/or fields) the request touches.
    `request_fingerprint` is computed by the trusted layer, not the client.
    """

    request_id: str
    revision: str
    subject_id: str
    asset_version: str
    scope: Sequence[str]
    operation: str
    recipient_id: str
    purpose: str = ""
    business_task_id: str = ""
    record_count: int = 0
    request_fingerprint: str = ""
    environment: str = "production"
    source_mode: SourceMode = SourceMode.SYNTHETIC
    schema_version: str = "m0"
    trace_id: str = ""

    def __post_init__(self) -> None:
        freeze_field(self, "scope")


@dataclass(frozen=True)
class AuthorizationSnapshot:
    """Authoritative authorization observed at a point in time (H2).

    `result` is the overall verdict; `UNKNOWN` must never be read as allowed.
    `allowed_scope` / `allowed_operations` / `allowed_recipients` bound what the
    subject may do; the judgment core compares the request against them.
    """

    authority_source: str
    snapshot_id: str
    subject_id: str
    data_domain: str
    result: AuthorizationResult
    allowed_scope: Sequence[str] = field(default_factory=tuple)
    allowed_operations: Sequence[str] = field(default_factory=tuple)
    allowed_recipients: Sequence[str] = field(default_factory=tuple)
    policy_version: str = ""
    observed_at: str = ""
    valid_until: str = ""
    environment: str = "production"
    source_mode: SourceMode = SourceMode.SYNTHETIC
    evidence_refs: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in ("allowed_scope", "allowed_operations", "allowed_recipients", "evidence_refs"):
            freeze_field(self, name)


@dataclass(frozen=True)
class SensitivityProfileRef:
    """Reference to mainline-1's sensitivity profile (H2).

    This mainline does not compute sensitivity; it only consumes a reference.
    An incomplete profile is marked, never defaulted to "not sensitive" (D4).
    """

    profile_id: str
    asset_version: str
    protection_level: str = "unknown"
    categories: Sequence[str] = field(default_factory=tuple)
    coverage: QualityState = QualityState.MISSING
    status: str = "unknown"
    detector_version: str = ""
    level_policy_version: str = ""
    source_mode: SourceMode = SourceMode.SYNTHETIC

    def __post_init__(self) -> None:
        freeze_field(self, "categories")


@dataclass(frozen=True)
class FeatureSnapshot:
    """Behavioural feature values at `as_of_time` (H2). Minimal in M0.

    `current_request_counted` records whether the current request is already
    folded into the windowed values, so downstream never double-counts (E4).
    """

    feature_set_version: str
    as_of_time: str
    values: Mapping[str, float] = field(default_factory=dict)
    units: Mapping[str, str] = field(default_factory=dict)
    missing: Sequence[str] = field(default_factory=tuple)
    data_watermark: str = ""
    current_request_counted: bool = False
    quality: QualityState = QualityState.OK
    baseline_ref: str = ""

    def __post_init__(self) -> None:
        for name in ("values", "units", "missing"):
            freeze_field(self, name)


@dataclass(frozen=True)
class BehaviorBaseline:
    """Per-subject or cohort baseline (H2). Placeholder shape for M0."""

    baseline_id: str
    version: str
    subject_or_cohort: str
    training_window: str = ""
    sample_count: int = 0
    method: str = ""
    scope: str = ""
    quality: QualityState = QualityState.INSUFFICIENT_HISTORY

    def __post_init__(self) -> None:  # no nested containers yet
        return None
