"""Trusted-source admission for production signing (review R3).

Production signing accepts only production-sourced inputs. A synthetic or
evaluation input reaching a production signing path is refused — the flag is set
by the trusted assembly layer, never trusted from a client. In a non-production
environment synthetic inputs are allowed, but the resulting authorization is not
a production authority and must not touch production quota write paths.
"""

from typing import Iterable, Optional

from ..contracts import SourceMode
from ..contracts import reason_codes as rc


def check_admission(environment: str, source_modes: Iterable[SourceMode]) -> Optional[str]:
    """Return a refusal reason code, or None when admission passes."""
    if environment == "production":
        if any(mode != SourceMode.PRODUCTION for mode in source_modes):
            return rc.ADMISSION_SYNTHETIC_IN_PRODUCTION
    return None
