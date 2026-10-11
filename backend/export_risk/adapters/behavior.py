"""Behaviour input adapters (regex spec D1.2).

A ``BehaviorProvider`` yields pure EventRecord/DeliveryRec objects for feature
computation. Two implementations: a Django-backed one over the M1 tables and an
in-memory synthetic one for tests and the experiment harness. The synthetic
provider is **non-production** input and must be tagged as such upstream.
"""

from datetime import datetime
from typing import List, Protocol, Sequence

from ..features import DeliveryRec, EventRecord


class BehaviorProvider(Protocol):
    """Protocol for behaviour event sources."""

    def fetch_events(self, subject_id: str, until: datetime) -> Sequence[EventRecord]: ...
    def fetch_deliveries(self, subject_id: str, until: datetime) -> Sequence[DeliveryRec]: ...
    def watermark(self, until: datetime) -> datetime: ...


class SyntheticBehaviorProvider:
    """In-memory provider for tests / experiments (non-production)."""

    def __init__(self, events: Sequence[EventRecord], deliveries: Sequence[DeliveryRec],
                 watermark_at: datetime):
        self._events = list(events)
        self._deliveries = list(deliveries)
        self._watermark = watermark_at

    def fetch_events(self, subject_id: str, until: datetime) -> Sequence[EventRecord]:
        # Dual-time: only events that both occurred and were *received* before
        # the knowledge cutoff are visible (review F9).
        return [e for e in self._events if e.occurred_at < until and e.received_at < until]

    def fetch_deliveries(self, subject_id: str, until: datetime) -> Sequence[DeliveryRec]:
        return [d for d in self._deliveries if d.occurred_at < until]

    def watermark(self, until: datetime) -> datetime:
        return min(self._watermark, until)


class DjangoBehaviorProvider:
    """Reads the M1 persistence tables and converts to pure records.

    Dedup is enforced at write time by BehaviorEvent.event_id uniqueness; here we
    only read and project. Simulated rows are preserved with their flag so the
    feature layer can decide whether to include them.
    """

    def fetch_events(self, subject_id: str, until: datetime) -> List[EventRecord]:
        from ..models import BehaviorEvent
        # Knowledge cutoff is dual-time: an event is historical only if it was
        # received before ``until`` as well as having occurred before it (F9).
        rows = BehaviorEvent.objects.filter(
            subject_id=subject_id, occurred_at__lt=until, received_at__lt=until
        )
        return [
            EventRecord(
                event_id=r.event_id, event_type=r.event_type,
                occurred_at=r.occurred_at, received_at=r.received_at,
                recipient_id=r.recipient_id, object_scope=tuple(r.object_scope or ()),
                record_count=r.record_count, is_simulated=r.is_simulated,
            )
            for r in rows
        ]

    def fetch_deliveries(self, subject_id: str, until: datetime) -> List[DeliveryRec]:
        from ..models import DeliveryRecord
        rows = DeliveryRecord.objects.filter(subject_id=subject_id, occurred_at__lt=until)
        return [
            DeliveryRec(
                delivery_id=r.delivery_id, occurred_at=r.occurred_at,
                delivered_record_count=r.delivered_record_count, is_simulated=r.is_simulated,
            )
            for r in rows
        ]

    def watermark(self, until: datetime) -> datetime:
        from django.db.models import Max
        from ..models import BehaviorEvent
        hi = BehaviorEvent.objects.filter(received_at__lt=until).aggregate(m=Max('received_at'))['m']
        return hi or until
