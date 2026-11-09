"""Shared immutable-version/CAS rules for both policy repositories."""
from data_security.contracts import PolicyStatus, ReasonCode
from data_security.contracts.schema import require


def check_write(snapshots, snapshot, expected_version):
    existing = next((item for item in snapshots if item.version == snapshot.version), None)
    if existing is None:
        require(expected_version == (snapshots[-1].version if snapshots else None),
                ReasonCode.IDEMPOTENCY_CONFLICT)
        return
    require(expected_version == existing.version and existing.content_hash == snapshot.content_hash,
            ReasonCode.IDEMPOTENCY_CONFLICT)
    if existing == snapshot:
        return
    require((existing.status, snapshot.status) in (
        (PolicyStatus.DRAFT, PolicyStatus.APPROVED),
        (PolicyStatus.DRAFT, PolicyStatus.RETIRED),
        (PolicyStatus.APPROVED, PolicyStatus.RETIRED)), ReasonCode.IDEMPOTENCY_CONFLICT)
    require(existing.approval is None or existing.approval == snapshot.approval,
            ReasonCode.IDEMPOTENCY_CONFLICT)
