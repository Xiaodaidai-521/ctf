"""Pure robust statistics for baselines (regex spec E6). No numpy, no clock."""

from typing import List, Optional, Sequence


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile (q in [0,100]) over unsorted values."""
    if not values:
        raise ValueError("percentile of empty sequence")
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    rank = (q / 100.0) * (len(xs) - 1)
    lo = int(rank)
    frac = rank - lo
    if lo + 1 >= len(xs):
        return float(xs[-1])
    return float(xs[lo] + (xs[lo + 1] - xs[lo]) * frac)


def median(values: Sequence[float]) -> float:
    return percentile(values, 50.0)


def iqr(values: Sequence[float]) -> float:
    """Inter-quartile range p75 - p25."""
    return percentile(values, 75.0) - percentile(values, 25.0)


def robust_deviation(x: float, med: float, spread: float) -> Optional[float]:
    """Robust deviation (x - median) / IQR.

    Returns None when spread is 0 **and** x differs from the median: the sample
    is degenerate and a numeric deviation would be misleading (not 0, not inf).
    """
    if spread > 0:
        return (x - med) / spread
    if x == med:
        return 0.0
    return None
