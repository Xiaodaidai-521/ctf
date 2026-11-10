"""Metadata for explicitly registered synthetic canaries, not user-supplied values."""
from dataclasses import dataclass
from typing import ClassVar

from .enums import Environment, ReasonCode
from .schema import DTO, reference, require


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CanarySeed(DTO):
    SCHEMA: ClassVar[str] = 'ds.canary-seed.v1'
    seed_id: str
    target_kind: str
    target_ref: str
    target_version: str
    environment: Environment
    domain: str

    def __post_init__(self):
        DTO.__post_init__(self)
        require(len(self.seed_id) == 32 and all(c in '0123456789abcdef' for c in self.seed_id))
        require(self.target_kind in ('knowledge', 'database', 'challenge'))
        require(self.environment in (Environment.TEST, Environment.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
        for value in (self.target_ref, self.target_version, self.domain):
            reference(value)
