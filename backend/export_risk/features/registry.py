"""Declarative feature registry (regex spec E4).

Every feature carries the 11 mandatory metadata items so completeness is
machine-checkable (a test enumerates the registry) and the feature-set version
hash is derivable. Ablation selects features by ``tags``. Pure Python; this is
input-prep metadata, not the judgment core.
"""

from dataclasses import dataclass, field
from typing import Sequence
import hashlib
import json


@dataclass(frozen=True)
class FeatureDefinition:
    """One behavioural feature and its full E4 metadata."""

    name: str                       # (1) name
    version: str                    # (1) version
    source: str                     # (2) source
    trust: str                      # (2) trust level
    subject_domain: str             # (3) subject + data domain
    unit: str                       # (4) unit
    window_seconds: int             # (5) window length (0 = pointwise / non-windowed)
    interval: str                   # (5) open/close interval, e.g. "[)"
    time_basis: str                 # (6) "occurred" | "received"
    watermark_policy: str           # (7) data cutoff / watermark rule
    dedup_method: str               # (8) dedup method
    counts_current_request: bool    # (9) is the current request already folded in
    missing_policy: str             # (10) missing-value handling
    late_policy: str                # (10) late-arrival handling
    method: str                     # (11) computation method
    limits: str                     # (11) applicability limits
    tags: Sequence[str] = field(default_factory=tuple)

    REQUIRED_META = (
        "name", "version", "source", "trust", "subject_domain", "unit",
        "interval", "time_basis", "watermark_policy", "dedup_method",
        "missing_policy", "late_policy", "method", "limits",
    )

    def metadata_gaps(self) -> list:
        """Return names of required string metadata that are empty."""
        gaps = []
        for attr in self.REQUIRED_META:
            value = getattr(self, attr)
            if isinstance(value, str) and not value.strip():
                gaps.append(attr)
        return gaps


# First-cut registry (DRAFT windows/params — not approved thresholds, E4/E3).
FEATURE_REGISTRY = (
    FeatureDefinition(
        name="req_count_short", version="v1", source="behavior_event", trust="medium",
        subject_domain="subject/export", unit="requests", window_seconds=600, interval="[)",
        time_basis="occurred", watermark_policy="max_received_at", dedup_method="event_id",
        counts_current_request=False, missing_policy="treat_missing_as_unknown_not_zero",
        late_policy="drop_after_watermark", method="count events in [as_of-10m, as_of)",
        limits="attempt volume, includes denied requests", tags=("quantity", "short_window"),
    ),
    FeatureDefinition(
        name="req_count_long", version="v1", source="behavior_event", trust="medium",
        subject_domain="subject/export", unit="requests", window_seconds=86400, interval="[)",
        time_basis="occurred", watermark_policy="max_received_at", dedup_method="event_id",
        counts_current_request=False, missing_policy="treat_missing_as_unknown_not_zero",
        late_policy="drop_after_watermark", method="count events in [as_of-24h, as_of)",
        limits="attempt volume, not delivery", tags=("quantity", "long_window", "cumulative"),
    ),
    FeatureDefinition(
        name="distinct_recipients_long", version="v1", source="behavior_event", trust="medium",
        subject_domain="subject/export", unit="recipients", window_seconds=86400, interval="[)",
        time_basis="occurred", watermark_policy="max_received_at", dedup_method="event_id",
        counts_current_request=False, missing_policy="treat_missing_as_unknown_not_zero",
        late_policy="drop_after_watermark", method="distinct recipient_id in [as_of-24h, as_of)",
        limits="recipient variety; empty recipient ignored", tags=("recipient", "long_window"),
    ),
    FeatureDefinition(
        name="distinct_objects_long", version="v1", source="behavior_event", trust="medium",
        subject_domain="subject/export", unit="objects", window_seconds=86400, interval="[)",
        time_basis="occurred", watermark_policy="max_received_at", dedup_method="event_id",
        counts_current_request=False, missing_policy="treat_missing_as_unknown_not_zero",
        late_policy="drop_after_watermark", method="distinct object ids over scope in window",
        limits="scope breadth; requires stable object ids", tags=("scope", "long_window", "cumulative"),
    ),
    FeatureDefinition(
        name="delivered_count_long", version="v1", source="delivery_record", trust="low",
        subject_domain="subject/export", unit="records", window_seconds=86400, interval="[)",
        time_basis="occurred", watermark_policy="telemetry_only", dedup_method="delivery_id",
        counts_current_request=False, missing_policy="no_telemetry_means_unknown_not_zero",
        late_policy="drop_after_watermark", method="sum delivered_record_count in window",
        limits="simulated ledgers excluded unless flagged; real delivery needs telemetry",
        tags=("quantity", "delivery"),
    ),
)


def registry_fingerprint(registry: Sequence[FeatureDefinition] = FEATURE_REGISTRY) -> str:
    """Deterministic content hash of the registry (feature-set version source).

    Derived from each feature's full metadata so any definition change produces a
    new fingerprint; order-independent (features sorted by name).
    """
    payload = [
        {k: (list(v) if isinstance(v, tuple) else v) for k, v in vars(f).items()}
        for f in sorted(registry, key=lambda d: d.name)
    ]
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
