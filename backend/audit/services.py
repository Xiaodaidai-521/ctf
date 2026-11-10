"""Services for writing and verifying tamper-evident audit ledger entries."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.db import transaction

from .legacy_hashes import (
    GENESIS_HASH, canonical_json, sha256_hex, compute_payload_hash, compute_entry_hash,
)
from .models import AuditLedgerEntry, AuditLedgerLock


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


class AuditLedgerService:
    """Write and verify audit ledger entries."""

    @staticmethod
    def append_entry(
        *, event_category: str, payload: Dict[str, Any], object_type: str = '',
        object_id: Any = '', actor=None, chain_version: Optional[str] = None,
    ) -> AuditLedgerEntry:
        """Compatibility facade; formal assembly requires a confirmed receipt."""
        from data_security.contracts import Durability, ReasonCode
        from data_security.contracts.schema import require
        from . import bridge
        if bridge.is_bound():
            require(chain_version in (None, 'v1'), ReasonCode.UNSUPPORTED_FORMAT)
            receipt = bridge.record(category=event_category, actor_id=getattr(actor, 'pk', None),
                                    object_id=object_id, durability=Durability.LEDGER_CONFIRMED)
            return AuditLedgerEntry.objects.get(pk=receipt.sequence)
        return AuditLedgerService._append_entry(event_category=event_category, payload=payload,
            object_type=object_type, object_id=object_id, actor=actor, chain_version=chain_version)

    @staticmethod
    @transaction.atomic
    def _append_entry(
        *,
        event_category: str,
        payload: Dict[str, Any],
        object_type: str = '',
        object_id: Any = '',
        actor=None,
        chain_version: Optional[str] = None,
    ) -> AuditLedgerEntry:
        """Internal v1 writer; Sink never calls the public compatibility facade."""
        from data_security.contracts import ReasonCode
        from data_security.contracts.schema import require
        chain_version = chain_version or getattr(settings, 'LEGAL_AUDIT_CHAIN_VERSION', 'v1')
        AuditLedgerLock.objects.get_or_create(key='default')
        lock = AuditLedgerLock.objects.select_for_update().get(key='default')
        require(lock.legacy_archive == {}, ReasonCode.AUDIT_UNAVAILABLE)
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
    def verify_chain(*, entries=None) -> LedgerVerificationResult:
        """Verify ordered entries; archive callers supply their bounded snapshot iterator."""
        errors: List[LedgerVerificationError] = []
        previous_hash = GENESIS_HASH
        if entries is None:
            row = AuditLedgerLock.objects.filter(key='default').values('legacy_archive').first()
            if row is not None and row['legacy_archive'] != {}:
                state = row['legacy_archive']
                actual = state.get('state') if type(state) is dict else None
                if actual not in ('quarantined', 'deleted'):
                    actual = 'unknown'
                # Hiding or removing the online source never creates a new genesis.
                return LedgerVerificationResult(is_valid=False, checked_count=0, errors=[
                    LedgerVerificationError(entry_id=0, field='source_state', expected='online-v1', actual=actual)])
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
