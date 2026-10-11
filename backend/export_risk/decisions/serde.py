"""Serialisation + digest helpers for decision persistence."""

import hashlib
import json
from typing import Iterable, Sequence

from ..contracts import Obligation


def obligation_to_dict(ob: Obligation) -> dict:
    return {
        "obligation_id": ob.obligation_id,
        "type": ob.type,
        "parameters": _plain(ob.parameters),
        "applicable_scope": ob.applicable_scope,
        "enforcement_stage": ob.enforcement_stage,
        "required_evidence": list(ob.required_evidence),
    }


def obligations_to_json(obligations: Sequence[Obligation]) -> list:
    return [obligation_to_dict(o) for o in obligations]


def _plain(value):
    """Recursively convert frozen views (MappingProxyType/tuple) to plain json."""
    if hasattr(value, "items"):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def digest(*parts) -> str:
    """Deterministic sha256 over the given parts (order-sensitive)."""
    blob = json.dumps([_plain(p) for p in parts], ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
