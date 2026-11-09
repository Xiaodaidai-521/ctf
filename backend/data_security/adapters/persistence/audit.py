"""Audit-domain persistence: durable events and the unchanged, unauthenticated v1 chain."""
from django.db import DatabaseError, transaction

from audit.models import AuditEvent, AuditLedgerEntry, AuditLedgerLock, SecurityAuditRecord
from audit.services import AuditLedgerService
from data_security.contracts import (AuditReceipt, AuditSink, ContractViolation, Durability,
                                     ProtectionError, ReasonCode, SecurityEvent)


class DjangoAuditSink(AuditSink):
    def __init__(self, *, clock):
        self.clock = clock

    def append(self, event: SecurityEvent, durability: Durability) -> AuditReceipt | ProtectionError:
        # Gateway accepts only M0 DTOs. This adapter never imports or calls it,
        # an outbox, ProtectionPort, or CryptoPort.authenticate.
        try:
            with transaction.atomic():
                wire = event.to_wire()
                row, _ = SecurityAuditRecord.objects.get_or_create(
                    event_id=event.event_id,
                    defaults={'event': wire, 'stored_at': self.clock(),
                        # A validated metadata-only SecurityEvent is already protected.
                        # Bypass the business write hook so auditing does not audit itself.
                        'audit_event': lambda: AuditEvent._base_manager.bulk_create([AuditEvent(
                            category='data_processing', level='INFO', security_state='sealed-v1',
                            security_revision=1, summary=event.kind.value, detail=wire)])[0]},
                )
                # Keep event-row -> ledger-singleton -> ledger-tail lock order.
                row = SecurityAuditRecord.objects.select_for_update().get(pk=row.pk)
                if row.event != wire:
                    return ProtectionError(schema_version=ProtectionError.SCHEMA,
                        code=ReasonCode.IDEMPOTENCY_CONFLICT, retryable=False,
                        trace_id=event.correlation_ref)
                entry = None
                if durability is Durability.LEDGER_CONFIRMED:
                    if row.ledger_entry_id is None:
                        row.ledger_entry = AuditLedgerService._append_entry(
                            event_category=event.kind.value, payload=wire,
                            object_type='data_security.event', object_id=event.event_id,
                            chain_version='v1')
                        row.save(update_fields=['ledger_entry'])
                    entry = row.ledger_entry
                return AuditReceipt(schema_version=AuditReceipt.SCHEMA,
                    event_id=event.event_id, durability=durability, stored_at=row.stored_at,
                    chain_version=entry.chain_version if entry else None,
                    entry_ref=f'audit/ledger/{entry.pk}' if entry else None,
                    sequence=entry.pk if entry else None,
                    entry_hash=entry.current_hash if entry else None, checkpoint_ref=None)
        except (DatabaseError, ContractViolation):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id=event.correlation_ref)

    def verify(self, chain_ref: str) -> AuditReceipt | ProtectionError:
        if chain_ref != 'v1':
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.UNSUPPORTED_FORMAT, retryable=False, trace_id='audit/verify')
        try:
            # Serialize against the same append lock while choosing the verified tail.
            with transaction.atomic():
                AuditLedgerLock.objects.get_or_create(key='default')
                AuditLedgerLock.objects.select_for_update().get(key='default')
                valid = AuditLedgerService.verify_chain().is_valid
                entry = AuditLedgerEntry.objects.order_by('-id').first()
                if not valid or entry is None or entry.chain_version != 'v1':
                    return ProtectionError(schema_version=ProtectionError.SCHEMA,
                        code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='audit/verify')
                row = SecurityAuditRecord.objects.filter(ledger_entry=entry).first()
                return AuditReceipt(schema_version=AuditReceipt.SCHEMA,
                    event_id=row.event_id if row else f'legacy/{entry.pk}',
                    durability=Durability.LEDGER_CONFIRMED, stored_at=entry.created_at,
                    chain_version='v1', entry_ref=f'audit/ledger/{entry.pk}', sequence=entry.pk,
                    entry_hash=entry.current_hash, checkpoint_ref=None)
        except (DatabaseError, ContractViolation):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='audit/verify')

    def checkpoint(self, chain_ref: str) -> ProtectionError:
        # No new-chain authentication or external anchor is claimed in phase 3.
        return ProtectionError(schema_version=ProtectionError.SCHEMA,
            code=ReasonCode.UNSUPPORTED_FORMAT, retryable=False, trace_id='audit/checkpoint')
