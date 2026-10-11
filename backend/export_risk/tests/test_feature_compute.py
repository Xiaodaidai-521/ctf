"""M1: pure windowed feature computation (E3/E4)."""

import unittest
from datetime import datetime, timedelta, timezone

from export_risk.contracts import QualityState
from export_risk.features import DeliveryRec, EventRecord, build_feature_snapshot
from export_risk.features.compute import compute_behavior_features, compute_delivery_features

AS_OF = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)


def ev(minutes_ago, recipient="r1", objects=("o1",), etype="export_request"):
    t = AS_OF - timedelta(minutes=minutes_ago)
    return EventRecord(
        event_id=f"e{minutes_ago}_{recipient}", event_type=etype,
        occurred_at=t, received_at=t, recipient_id=recipient, object_scope=objects,
    )


class ComputeTests(unittest.TestCase):
    def test_short_and_long_window_counts(self):
        events = [ev(1), ev(5), ev(30), ev(600)]  # 1m,5m,30m,600m(=10h)
        vals = compute_behavior_features(events, AS_OF)
        self.assertEqual(vals["req_count_short"], 2.0)   # within 10m: 1m,5m
        self.assertEqual(vals["req_count_long"], 4.0)    # within 24h: all

    def test_half_open_window_excludes_current_instant(self):
        at_as_of = EventRecord("now", "export_request", AS_OF, AS_OF)
        at_start = ev(10)  # exactly 10m ago = window start, included by "["
        vals = compute_behavior_features([at_as_of, at_start], AS_OF)
        self.assertEqual(vals["req_count_short"], 1.0)   # as_of excluded, start included

    def test_distinct_recipients_and_objects(self):
        events = [ev(1, "r1", ("o1", "o2")), ev(2, "r2", ("o2", "o3")), ev(3, "r1", ("o1",))]
        vals = compute_behavior_features(events, AS_OF)
        self.assertEqual(vals["distinct_recipients_long"], 2.0)
        self.assertEqual(vals["distinct_objects_long"], 3.0)

    def test_delivery_excludes_simulated_unless_requested(self):
        deliveries = [
            DeliveryRec("d1", AS_OF - timedelta(hours=1), 100, is_simulated=True),
            DeliveryRec("d2", AS_OF - timedelta(hours=2), 40, is_simulated=False),
        ]
        self.assertEqual(compute_delivery_features(deliveries, AS_OF)["delivered_count_long"], 40.0)
        self.assertEqual(
            compute_delivery_features(deliveries, AS_OF, include_simulated=True)["delivered_count_long"],
            140.0,
        )

    def test_snapshot_marks_missing_delivery_and_staleness(self):
        events = [ev(1)]
        snap = build_feature_snapshot(events, [], AS_OF, data_watermark=AS_OF - timedelta(hours=3))
        self.assertIn("delivered_count_long", snap.missing)      # no telemetry => unknown not zero
        self.assertEqual(snap.quality, QualityState.STALE)       # watermark behind as_of
        self.assertFalse(snap.current_request_counted)


if __name__ == "__main__":
    unittest.main()
