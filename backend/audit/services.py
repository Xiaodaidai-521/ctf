"""Services for writing and verifying tamper-evident audit ledger entries."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.db import transaction

from .models import AuditLedgerEntry, AuditLedgerLock


GENESIS_HASH = '0' * 64


@dataclass(frozen=True)
class LedgerVerificationError:
    """A single hash-chain verification error."""

    entry_id: int
    field: str
    expected: str
    actual: str


@dataclass(frozen=True)
class LedgerVerificationResult:
    """Result returned by the hash-chain verifier."""

    is_valid: bool
    checked_count: int
    errors: List[LedgerVerificationError]


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


class AuditLedgerService:
    """Write and verify audit ledger entries."""

    @staticmethod
    @transaction.atomic
    def append_entry(
        *,
        event_category: str,
        payload: Dict[str, Any],
        object_type: str = '',
        object_id: Any = '',
        actor=None,
        chain_version: Optional[str] = None,
    ) -> AuditLedgerEntry:
        """Append a new ledger entry to the hash chain."""
        chain_version = chain_version or getattr(settings, 'LEGAL_AUDIT_CHAIN_VERSION', 'v1')
        AuditLedgerLock.objects.get_or_create(key='default')
        AuditLedgerLock.objects.select_for_update().get(key='default')
        previous = (
            AuditLedgerEntry.objects.select_for_update()
            .order_by('-id')
            .first()
        )
        previous_hash = previous.current_hash if previous else GENESIS_HASH
        payload_hash = compute_payload_hash(payload)
        current_hash = compute_entry_hash(
            previous_hash=previous_hash,
            payload_hash=payload_hash,
            event_category=event_category,
            object_type=object_type,
            object_id=str(object_id or ''),
            actor_id=getattr(actor, 'id', None),
            chain_version=chain_version,
        )
        return AuditLedgerEntry.objects.create(
            event_category=event_category,
            object_type=object_type or '',
            object_id=str(object_id or ''),
            actor=actor if getattr(actor, 'is_authenticated', True) else None,
            payload=payload or {},
            payload_hash=payload_hash,
            previous_hash=previous_hash,
            current_hash=current_hash,
            chain_version=chain_version,
        )

    @staticmethod
    def verify_chain() -> LedgerVerificationResult:
        """Verify all ledger entries in insertion order."""
        errors: List[LedgerVerificationError] = []
        previous_hash = GENESIS_HASH
        entries = AuditLedgerEntry.objects.order_by('id').select_related('actor')

        checked_count = 0
        for entry in entries:
            checked_count += 1
            expected_payload_hash = compute_payload_hash(entry.payload)
            if entry.payload_hash != expected_payload_hash:
                errors.append(LedgerVerificationError(
                    entry_id=entry.id,
                    field='payload_hash',
                    expected=expected_payload_hash,
                    actual=entry.payload_hash,
                ))

            if entry.previous_hash != previous_hash:
                errors.append(LedgerVerificationError(
                    entry_id=entry.id,
                    field='previous_hash',
                    expected=previous_hash,
                    actual=entry.previous_hash,
                ))

            expected_current_hash = compute_entry_hash(
                previous_hash=entry.previous_hash,
                payload_hash=entry.payload_hash,
                event_category=entry.event_category,
                object_type=entry.object_type,
                object_id=entry.object_id,
                actor_id=entry.actor_id,
                chain_version=entry.chain_version,
            )
            if entry.current_hash != expected_current_hash:
                errors.append(LedgerVerificationError(
                    entry_id=entry.id,
                    field='current_hash',
                    expected=expected_current_hash,
                    actual=entry.current_hash,
                ))

            previous_hash = entry.current_hash

        return LedgerVerificationResult(
            is_valid=not errors,
            checked_count=checked_count,
            errors=errors,
        )
