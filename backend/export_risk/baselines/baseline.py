"""Baseline construction with cold-start fallback (regex spec E6).

Replay-safe: only observations at/before the training cutoff are used, so a
historical replay never sees future data. Cold-start order: own history ->
cohort -> explicit degrade. "No history" is never treated as "normal": an
insufficient baseline is marked INSUFFICIENT_HISTORY and yields no deviation.

Cohort is keyed on an export position / business function supplied by the
authorization source — **never** CTFUser.role (that is a teaching role, not a
security position; Stage-1 finding on D3). Min-sample thresholds are DRAFT.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Optional, Sequence

from ..contracts import BehaviorBaseline, QualityState
from . import statistics as st

# DRAFT thresholds — not approved parameters (regex spec E6 / review R5).
MIN_SUBJECT_SAMPLES = 5
MIN_COHORT_SAMPLES = 20


@dataclass(frozen=True)
class Observation:
    """One historical feature observation used to fit a baseline."""

    subject_id: str
    cohort_key: str
    as_of: datetime
    values: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class BaselineStats:
    """Per-feature robust statistics."""

    feature_name: str
    median: float
    p25: float
    p75: float
    iqr: float
    sample_count: int


@dataclass(frozen=True)
class BaselineBundle:
    """A BehaviorBaseline plus its per-feature statistics."""

    baseline: BehaviorBaseline
    stats: Mapping[str, BaselineStats] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.baseline.quality != QualityState.INSUFFICIENT_HISTORY


def _stats_for(observations: Sequence[Observation], feature_names: Sequence[str]) -> dict:
    out = {}
    for name in feature_names:
        series = [o.values[name] for o in observations if name in o.values]
        if not series:
            continue
        out[name] = BaselineStats(
            feature_name=name, median=st.median(series),
            p25=st.percentile(series, 25.0), p75=st.percentile(series, 75.0),
            iqr=st.iqr(series), sample_count=len(series),
        )
    return out


def build_baseline(
    observations: Sequence[Observation],
    *,
    subject_id: str,
    cohort_key: str,
    cutoff: datetime,
    feature_names: Sequence[str],
    version: str = "bl-v1",
    min_subject: int = MIN_SUBJECT_SAMPLES,
    min_cohort: int = MIN_COHORT_SAMPLES,
) -> BaselineBundle:
    """Build a baseline, preferring own history then cohort, else degrade."""
    # Replay safety: discard anything after the cutoff.
    past = [o for o in observations if o.as_of <= cutoff]

    own = [o for o in past if o.subject_id == subject_id]
    if len(own) >= min_subject:
        return _bundle(own, "subject", subject_id, cutoff, feature_names, version, QualityState.OK)

    cohort = [o for o in past if o.cohort_key == cohort_key]
    if len(cohort) >= min_cohort:
        return _bundle(cohort, "cohort", cohort_key, cutoff, feature_names, version,
                       QualityState.INSUFFICIENT_HISTORY if len(own) == 0 else QualityState.OK)

    # Degrade: not enough data anywhere. Do not fabricate a "normal" baseline.
    return BaselineBundle(
        baseline=BehaviorBaseline(
            baseline_id=f"{subject_id}:degraded", version=version,
            subject_or_cohort=subject_id, training_window=f"<= {cutoff.isoformat()}",
            sample_count=len(own), method="robust_quartiles", scope="degraded",
            quality=QualityState.INSUFFICIENT_HISTORY,
        ),
        stats={},
    )


def _bundle(obs, scope, who, cutoff, feature_names, version, quality) -> BaselineBundle:
    return BaselineBundle(
        baseline=BehaviorBaseline(
            baseline_id=f"{who}:{scope}", version=version, subject_or_cohort=who,
            training_window=f"<= {cutoff.isoformat()}", sample_count=len(obs),
            method="robust_quartiles", scope=scope, quality=quality,
        ),
        stats=_stats_for(obs, feature_names),
    )


def compute_deviations(bundle: BaselineBundle, values: Mapping[str, float]) -> Mapping[str, Optional[float]]:
    """Robust deviation of current values vs baseline; {} when unusable.

    A feature maps to None when its baseline spread is degenerate (handled by
    robust_deviation); callers must treat None as "cannot rank", not zero.
    """
    if not bundle.usable:
        return {}
    out = {}
    for name, value in values.items():
        stats = bundle.stats.get(name)
        if stats is None:
            continue
        out[name] = st.robust_deviation(value, stats.median, stats.iqr)
    return out
