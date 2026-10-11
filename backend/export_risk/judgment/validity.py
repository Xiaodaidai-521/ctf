"""Pure authorization validity over injected, timezone-aware timestamps.

No clock/DB reads: parsing establishes an absolute instant, then the supplied
``evaluation_time`` is checked against [observed_at, valid_until).
"""

from datetime import datetime
from typing import Optional

from ..contracts import AuthorizationSnapshot
from ..contracts import reason_codes as rc


def parse_aware_timestamp(value: str) -> Optional[datetime]:
    """Parse an ISO-8601 instant; blank, malformed or timezone-free -> None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
        if parsed.utcoffset() is None:
            return None
        return parsed
    except (TypeError, ValueError, OverflowError):
        return None


def authorization_validity(
    authorization: AuthorizationSnapshot, evaluation_time: str
) -> Optional[str]:
    """Return a degrade reason, or None for a currently valid grant.

    All three times must establish absolute instants; naive/blank observation
    times are not ignored. The expiry boundary is exclusive.
    """
    evaluated = parse_aware_timestamp(evaluation_time)
    valid_until = parse_aware_timestamp(authorization.valid_until)
    observed_at = parse_aware_timestamp(authorization.observed_at)
    if evaluated is None or valid_until is None or observed_at is None:
        return rc.DEGRADE_AUTHORIZATION_VALIDITY_UNKNOWN
    if observed_at >= valid_until or observed_at > evaluated:
        return rc.DEGRADE_AUTHORIZATION_VALIDITY_UNKNOWN
    if evaluated >= valid_until:
        return rc.DEGRADE_AUTHORIZATION_EXPIRED
    return None
