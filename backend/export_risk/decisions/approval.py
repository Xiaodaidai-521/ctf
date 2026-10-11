"""Approval query adapter (regex spec D1.6; non-production test adapter).

The in-memory provider is for tests only and is explicitly **not** a production
authority. A real approval owner is wired later (OQ-4). Keeping it in-memory is
acceptable because approval status is a lookup, not a concurrency-critical
atomic reservation (contrast export_quota, which needs a DB row lock).
"""

from typing import Protocol


class ApprovalProvider(Protocol):
    is_production_authority: bool

    def status(self, decision_id: str, request_fingerprint: str) -> str:
        """Return 'approved' | 'pending' | 'none' | 'revoked'."""
        ...


class InMemoryApprovalProvider:
    """Test adapter. NON-PRODUCTION."""

    is_production_authority = False

    def __init__(self):
        self._by_decision = {}

    def set_status(self, decision_id: str, status: str) -> None:
        self._by_decision[decision_id] = status

    def status(self, decision_id: str, request_fingerprint: str) -> str:
        return self._by_decision.get(decision_id, "none")
