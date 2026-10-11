"""Transactional outbox + audit-ledger relay (regex spec H7; review R6).

`enqueue` must be called inside the business transaction. `relay_pending` drains
each pending row in a **single** transaction (claim row -> append ledger -> mark
sent), so a crash cannot leave a ledger entry without the sent mark, nor the
reverse. `event_id` uniqueness gives at-least-once consumers a dedup key.
"""

from django.db import transaction
from django.utils import timezone

from ..models import EventOutbox


def enqueue(event_id: str, event_type: str, payload: dict) -> EventOutbox:
    """Record a decision-level event. Call within the business transaction."""
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
            entry = AuditLedgerService.append_entry(
                event_category=row.event_type,
                payload={"event_id": row.event_id, **(row.payload or {})},
                object_type="export_risk.event",
                object_id=row.event_id,
            )
            row.status = "sent"
            row.ledger_hash = entry.current_hash
            row.sent_at = timezone.now()
            row.save(update_fields=["status", "ledger_hash", "sent_at"])
            relayed += 1
    return relayed
