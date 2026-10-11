"""Hard-constraint evaluation (regex spec E2, invariant D4).

Explicit over-authorization is denied here **without** any feature, baseline or
model. A low model score can never cancel a hard deny. Pure functions only.

Design: hard constraints only ever produce a DENY. They never allow. An
authorization result of UNKNOWN produces no hard deny (lack of info is not a
breach); the core degrades that to defer/require_approval instead.
"""

from dataclasses import dataclass, field
from typing import List, Sequence

from ..contracts import AuthorizationResult, AuthorizationSnapshot, ExportRequestSnapshot
from ..contracts import reason_codes as rc


@dataclass(frozen=True)
class HardConstraintOutcome:
    """Structured result of hard-constraint evaluation."""

    triggered: bool
    reason_codes: Sequence[str] = field(default_factory=tuple)


def evaluate_hard_constraints(
    request: ExportRequestSnapshot,
    authorization: AuthorizationSnapshot,
) -> HardConstraintOutcome:
    """Deny when the request provably exceeds an authoritative authorization."""
    codes: List[str] = []

    # The authorization must be bound to the requesting subject. Presenting
    # another subject's authorization is a breach, not a lack of information ->
    # deny (review F2), regardless of the authorization's own result.
    if authorization.subject_id != request.subject_id:
        codes.append(rc.HARD_AUTHORIZATION_SUBJECT_MISMATCH)

    if authorization.result == AuthorizationResult.FORBIDDEN:
        codes.append(rc.HARD_AUTHORIZATION_FORBIDDEN)

    # Envelope checks require an authoritative allow-list. Only an AUTHORIZED
    # result carries one; UNKNOWN is handled by the core as a degrade (defer).
    if authorization.result == AuthorizationResult.AUTHORIZED:
        if request.recipient_id not in set(authorization.allowed_recipients):
            codes.append(rc.HARD_RECIPIENT_FORBIDDEN)
        if request.operation not in set(authorization.allowed_operations):
            codes.append(rc.HARD_OPERATION_FORBIDDEN)
        if not set(request.scope) <= set(authorization.allowed_scope):
            codes.append(rc.HARD_SCOPE_EXCEEDED)

    return HardConstraintOutcome(triggered=bool(codes), reason_codes=tuple(codes))
