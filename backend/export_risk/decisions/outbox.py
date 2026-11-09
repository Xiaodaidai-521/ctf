"""Transactional outbox + audit-ledger relay (regex spec H7; review R6).

`enqueue` must be called inside the business transaction. `relay_pending` drains
each pending row in a **single** transaction (claim row -> append ledger -> mark
sent), so a crash cannot leave a ledger entry without the sent mark, nor the
reverse. `event_id` uniqueness gives at-least-once consumers a dedup key.
"""

from django.db import transaction
from django.utils import timezone

from data_security.contracts import (AuditPort, AuditReceipt, ContractViolation, Durability,
    EventKind, Outcome, PolicyBinding, ProtectionError, ReasonCode, SecurityEvent)
from data_security.contracts.schema import require

from ..models import EventOutbox


_binding = None


def bind(*, audit: AuditPort, policy_binding: PolicyBinding, clock):
    """B injects the sole gateway; relay never imports its implementation."""
    require(type(policy_binding) is PolicyBinding and callable(clock), ReasonCode.INVALID_TYPE)
    global _binding
    _binding = (audit, policy_binding, clock)


def _event(event_id, event_type, at):
    require(event_type in ('decision.issued', 'execution.authorized'), ReasonCode.UNSUPPORTED_FORMAT)
    return SecurityEvent(schema_version=SecurityEvent.SCHEMA, event_id=event_id,
        kind=EventKind.AUTHORIZATION, actor_ref='actor/unspecified', object_ref='export_risk/event',
        object_version=event_type, outcome=Outcome.UNKNOWN, occurred_at=at,
        counts=(), policy_binding=_binding[1], algorithm_versions=(), key_versions=(),
        correlation_ref=event_id, reason=None)


def enqueue(event_id: str, event_type: str, payload: dict) -> EventOutbox:
    """Record a decision-level event. Call within the business transaction."""
    if _binding is not None:
        # No arbitrary decision detail or authentication material enters the queue.
        wire = _event(event_id, event_type, _binding[2]()).to_wire()
        row, created = EventOutbox.objects.get_or_create(event_id=event_id,
            defaults={'event_type': event_type, 'payload': wire, 'status': 'pending'})
        if not created:
            # Re-enqueueing the same event does not change its first occurrence time.
            require(row.event_type == event_type and
                    {**row.payload, 'occurred_at': wire['occurred_at']} == wire,
                    ReasonCode.IDEMPOTENCY_CONFLICT)
        return row
    return EventOutbox.objects.create(
        event_id=event_id, event_type=event_type, payload=payload, status="pending"
    )


def relay_pending(limit: int = 100) -> int:
    """Append pending events to the audit ledger and mark them sent.

    Returns the number relayed. Each row is processed in its own transaction so
    the ledger append and the sent-mark commit atomically together.
    """
    from audit.services import AuditLedgerService

    pending_ids = list(
        EventOutbox.objects.filter(status="pending").order_by("id").values_list("id", flat=True)[:limit]
    )
    relayed = 0
    for row_id in pending_ids:
        with transaction.atomic():
            row = EventOutbox.objects.select_for_update().get(id=row_id)
            if row.status != "pending":  # already relayed by a concurrent worker
                continue
            if _binding is not None:
                if row.payload.get('schema_version') == SecurityEvent.SCHEMA:
                    event = SecurityEvent.from_wire(row.payload)
                    require(event.event_id == row.event_id, ReasonCode.IDEMPOTENCY_CONFLICT)
                else:
                    # Pre-assembly pending events are projected, not passed through.
                    event = _event(row.event_id, row.event_type, row.created_at)
                receipt = _binding[0].record(event, Durability.LEDGER_CONFIRMED)
                if type(receipt) is ProtectionError:
                    raise ContractViolation(receipt.code)
                require(type(receipt) is AuditReceipt and receipt.event_id == row.event_id
                        and receipt.durability is Durability.LEDGER_CONFIRMED,
                        ReasonCode.AUDIT_UNAVAILABLE)
                row.ledger_hash = receipt.entry_hash
                row.payload = event.to_wire()
                row.sent_at = _binding[2]()
            else:
                entry = AuditLedgerService.append_entry(
                    event_category=row.event_type,
                    payload={"event_id": row.event_id, **(row.payload or {})},
                    object_type="export_risk.event",
                    object_id=row.event_id,
                )
                row.ledger_hash = entry.current_hash
                row.sent_at = timezone.now()
            row.status = "sent"
            row.save(update_fields=["status", "ledger_hash", "sent_at", "payload"])
            relayed += 1
    return relayed
