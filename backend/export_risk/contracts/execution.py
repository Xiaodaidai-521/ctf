"""Execution-preparation result contracts (regex spec H4). Frozen, no Django."""

from dataclasses import dataclass, field
from typing import Sequence

from .assessment import Obligation
from .enums import Disposition
from .freezing import freeze_field


@dataclass(frozen=True)
class NotExecutable:
    """The request cannot be executed now (deny / require_approval / defer)."""

    disposition: Disposition
    reason_codes: Sequence[str] = field(default_factory=tuple)
    approval_request_id: str = ""
    kind: str = "not_executable"

    def __post_init__(self):
        freeze_field(self, "reason_codes")


@dataclass(frozen=True)
class ExecutionAuthorization:
    """An authorization the executor may claim exactly once (H4, review R1).

    Carrying a `reservation_id` and `valid_until`; the executor must re-confirm
    the reservation is still active at execution start. Binds request/asset/
    profile/scope so a stale authorization cannot be reused for a new decision.
    """

    authorization_id: str
    execution_id: str
    decision_id: str
    request_fingerprint: str
    asset_version: str
    profile_id: str
    scope: Sequence[str] = field(default_factory=tuple)
    obligations: Sequence[Obligation] = field(default_factory=tuple)
    plan_id: str = ""
    plan_hash: str = ""
    reservation_id: str = ""
    valid_until: str = ""
    kind: str = "executable"

    def __post_init__(self):
        freeze_field(self, "scope")
        freeze_field(self, "obligations")
