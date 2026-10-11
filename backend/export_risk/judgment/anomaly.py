"""Pure anomaly signal selection (regex spec E7).

M3 has no scikit-learn (arm C model deferred). The signal is either an injected
model score (when input-prep supplied one) or a robust-deviation aggregate over
the ``dev::`` feature keys. The method and model-availability are reported so an
unavailable model is surfaced, never silently treated as "no anomaly" (I6).
"""

from typing import Mapping, Optional, Tuple

MODEL_KEY = "anomaly::model"
DEV_PREFIX = "dev::"


def anomaly_signal(values: Mapping[str, object]) -> Tuple[Optional[float], str, bool]:
    """Return (score, method, model_available)."""
    if MODEL_KEY in values and values[MODEL_KEY] is not None:
        return float(values[MODEL_KEY]), "injected_model", True
    devs = [abs(float(v)) for k, v in values.items()
            if k.startswith(DEV_PREFIX) and v is not None]
    if devs:
        return max(devs), "robust_deviation_aggregate", False
    return None, "none", False
