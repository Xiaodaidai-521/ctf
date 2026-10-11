"""M1: persistence semantics — event dedup and Django-backed feature snapshot."""

from datetime import datetime, timedelta, timezone

from django.db import IntegrityError, transaction
from django.test import TestCase

from export_risk.adapters import DjangoBehaviorProvider
from export_risk.features import build_feature_snapshot
from export_risk.models import BehaviorEvent, DeliveryRecord

AS_OF = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)


class IngestionTests(TestCase):
    def _event(self, event_id, minutes_ago, recipient="r1", objects=("o1",)):
        t = AS_OF - timedelta(minutes=minutes_ago)
        return BehaviorEvent.objects.create(
            event_id=event_id, subject_id="u1", event_type="export_request",
            occurred_at=t, received_at=t, source="synthetic",
            object_scope=list(objects), recipient_id=recipient, record_count=10,
        )

    def test_event_id_dedup_is_enforced(self):
        self._event("dup", 5)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._event("dup", 6)  # same event_id -> rejected (E4 dedup)

    def test_django_provider_builds_snapshot(self):
        self._event("e1", 1, "r1", ("o1", "o2"))
        self._event("e2", 5, "r2", ("o2",))
        DeliveryRecord.objects.create(
            delivery_id="d1", request_id="req1", subject_id="u1", recipient_id="r1",
            delivered_record_count=25, is_simulated=False, occurred_at=AS_OF - timedelta(hours=1),
            source="telemetry",
        )
        provider = DjangoBehaviorProvider()
        events = provider.fetch_events("u1", AS_OF)
        deliveries = provider.fetch_deliveries("u1", AS_OF)
        watermark = provider.watermark(AS_OF)

        snap = build_feature_snapshot(events, deliveries, AS_OF, data_watermark=watermark)
        self.assertEqual(snap.values["req_count_short"], 2.0)
        self.assertEqual(snap.values["distinct_recipients_long"], 2.0)
        self.assertEqual(snap.values["distinct_objects_long"], 2.0)
        self.assertEqual(snap.values["delivered_count_long"], 25.0)  # real telemetry
        self.assertNotIn("delivered_count_long", snap.missing)

    def test_watermark_is_max_received_at(self):
        self._event("e1", 10)
        self._event("e2", 2)
        provider = DjangoBehaviorProvider()
        self.assertEqual(provider.watermark(AS_OF), AS_OF - timedelta(minutes=2))
