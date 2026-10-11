"""Request/profile/environment consistency checks (regex spec E2 step 1).

Pure functions over snapshots. Returns reason codes for any mismatch; an empty
list means consistent. No clock, no DB, no settings.
"""

from typing import List

from ..contracts import AuthorizationSnapshot, ExportRequestSnapshot, SensitivityProfileRef
from ..contracts import reason_codes as rc


def check_consistency(
    request: ExportRequestSnapshot,
    profile: SensitivityProfileRef,
    authorization: AuthorizationSnapshot,
) -> List[str]:
    """Return reason codes for cross-input inconsistencies (safe-side)."""
    codes: List[str] = []

    # The sensitivity profile must describe the same asset version as the request;
    # otherwise the sensitivity evidence does not apply to what is being exported.
    if profile.asset_version and profile.asset_version != request.asset_version:
        codes.append(rc.CONSISTENCY_ASSET_VERSION_MISMATCH)

    # Inputs assembled from different environments must not be fused into one
    # verdict (review R3). Environment identity is authoritative, not the client.
    environments = {request.environment, authorization.environment}
    if len(environments) > 1:
        codes.append(rc.CONSISTENCY_ENVIRONMENT_MISMATCH)

    return codes
