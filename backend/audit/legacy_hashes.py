"""Frozen v1 audit hashes, without settings or storage imports.

These byte rules verify old evidence; they are not the authenticated v2 format.
"""
import hashlib
import json
from typing import Any, Dict, Optional


GENESIS_HASH = '0' * 64


def canonical_json(value: Dict[str, Any]) -> str:
    """Return deterministic JSON used for hashing audit payloads."""
    return json.dumps(
        value or {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        default=str,
    )


def sha256_hex(value: str) -> str:
    """Return a SHA-256 hex digest for text input."""
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Compute the deterministic hash of an audit payload."""
    return sha256_hex(canonical_json(payload))


def compute_entry_hash(
    *,
    previous_hash: str,
    payload_hash: str,
    event_category: str,
    object_type: str,
    object_id: str,
    actor_id: Optional[int],
    chain_version: str,
) -> str:
    """Compute the current hash for a ledger entry."""
    material = canonical_json({
        'previous_hash': previous_hash or GENESIS_HASH,
        'payload_hash': payload_hash,
        'event_category': event_category,
        'object_type': object_type or '',
        'object_id': str(object_id or ''),
        'actor_id': actor_id,
        'chain_version': chain_version,
    })
    return sha256_hex(material)
