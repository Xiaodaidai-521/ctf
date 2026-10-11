"""Pure windowed feature computation (regex spec E3/E4).

Operates on lightweight frozen records (not Django models), with ``as_of_time``
injected explicitly — no clock, no DB. The Django-backed adapter converts
BehaviorEvent/DeliveryRecord rows into these records. Produces a
``FeatureSnapshot`` contract.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping, Optional, Sequence

from ..contracts import FeatureSnapshot, QualityState
from .registry import FEATURE_REGISTRY

_BY_NAME = {f.name: f for f in FEATURE_REGISTRY}

# Only genuine export-request attempts count toward request/behaviour features;
# denial/delivery/share-access are distinct lifecycle events (review F10).
_REQUEST_EVENT_TYPE = "export_request"


@dataclass(frozen=True)
class EventRecord:
    """Minimal behaviour event for pure computation."""

    event_id: str
    event_type: str
    occurred_at: datetime
    received_at: datetime
    recipient_id: str = ""
    object_scope: Sequence[str] = field(default_factory=tuple)
    record_count: int = 0
    is_simulated: bool = False


@dataclass(frozen=True)
class DeliveryRec:
    """Minimal delivery telemetry record for pure computation."""

    delivery_id: str
    occurred_at: datetime
    delivered_record_count: int = 0
    is_simulated: bool = True


def _in_window(ts: datetime, as_of: datetime, window_seconds: int) -> bool:
    # Half-open [as_of - window, as_of): current instant excluded (interval "[)").
    start = as_of - timedelta(seconds=window_seconds)
    return start <= ts < as_of


def compute_behavior_features(
    events: Sequence[EventRecord], as_of: datetime, *, include_simulated: bool = False
) -> Mapping[str, float]:
    """Compute the 4 behaviour-sourced features over their windows.

    An event contributes only when it is a genuine export-request attempt (F10),
    was *received* before ``as_of`` (dual-time knowledge cutoff, F9), and —
    unless ``include_simulated`` — is not a simulated ledger row (F11).
    """
    def _eligible(e: EventRecord, window_seconds: int) -> bool:
        if e.received_at >= as_of:                     # not yet known at as_of (F9)
            return False
        if e.is_simulated and not include_simulated:   # simulated excluded by default (F11)
            return False
        if e.event_type != _REQUEST_EVENT_TYPE:        # export requests only (F10)
            return False
        return _in_window(e.occurred_at, as_of, window_seconds)

    out = {}
    for name in ("req_count_short", "req_count_long", "distinct_recipients_long", "distinct_objects_long"):
        fdef = _BY_NAME[name]
        in_win = [e for e in events if _eligible(e, fdef.window_seconds)]
        if name in ("req_count_short", "req_count_long"):
            out[name] = float(len(in_win))
        elif name == "distinct_recipients_long":
            out[name] = float(len({e.recipient_id for e in in_win if e.recipient_id}))
        elif name == "distinct_objects_long":
            objects = set()
            for e in in_win:
                objects.update(e.object_scope)
            out[name] = float(len(objects))
    return out


def compute_delivery_features(
    deliveries: Sequence[DeliveryRec], as_of: datetime, include_simulated: bool = False
) -> Mapping[str, float]:
    """Compute delivered volume. Simulated ledgers excluded unless requested."""
    fdef = _BY_NAME["delivered_count_long"]
    total = 0.0
    for d in deliveries:
        if d.is_simulated and not include_simulated:
            continue
        if _in_window(d.occurred_at, as_of, fdef.window_seconds):
            total += float(d.delivered_record_count)
    return {"delivered_count_long": total}


def build_feature_snapshot(
    events: Sequence[EventRecord],
    deliveries: Sequence[DeliveryRec],
    as_of: datetime,
    data_watermark: datetime,
    feature_set_version: str = "fs-v1",
    include_simulated_delivery: bool = False,
    include_simulated_behavior: bool = False,
) -> FeatureSnapshot:
    """Assemble a FeatureSnapshot, marking staleness when data lags as_of."""
    values = dict(compute_behavior_features(events, as_of, include_simulated=include_simulated_behavior))
    values.update(compute_delivery_features(deliveries, as_of, include_simulated_delivery))
    units = {f.name: f.unit for f in FEATURE_REGISTRY}

    # Missing vs zero: if the watermark has not caught up to as_of, downstream
    # must treat windowed values as possibly incomplete (not a confirmed zero).
    stale = data_watermark < as_of
    missing = tuple()
    if not deliveries:
        missing = ("delivered_count_long",)  # no telemetry => unknown, not zero

    return FeatureSnapshot(
        feature_set_version=feature_set_version,
        as_of_time=as_of.isoformat(),
        values=values,
        units=units,
        missing=missing,
        data_watermark=data_watermark.isoformat(),
        current_request_counted=False,
        quality=QualityState.STALE if stale else QualityState.OK,
    )
