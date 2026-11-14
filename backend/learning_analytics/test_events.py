from types import SimpleNamespace
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase

from users.models import CTFUser
from .events import record_learning_event
from .models import LearningBehaviorEvent


class TeachingEventCompatibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = CTFUser.objects.create_user(username='event-compatibility', role='student')

    def test_legacy_events_without_ids_remain_independent(self):
        for event_id in (None, ''):
            with self.subTest(event_id=event_id):
                first = record_learning_event(self.student, 'resource_retrieved', event_id=event_id)
                second = record_learning_event(self.student, 'resource_retrieved', event_id=event_id)
                self.assertNotEqual(first.pk, second.pk)
                self.assertIsNone(first.event_id)

    def test_strict_event_write_failure_is_not_reported_as_success(self):
        with patch.object(LearningBehaviorEvent.objects, 'create', side_effect=DatabaseError('unavailable')):
            with self.assertRaises(DatabaseError):
                record_learning_event(self.student, 'hint_requested', event_id='strict-failure', strict=True)
            with self.assertLogs('learning_analytics.events', level='ERROR'):
                self.assertIsNone(record_learning_event(self.student, 'resource_retrieved'))
        self.assertFalse(LearningBehaviorEvent.objects.exists())

    def test_concurrent_duplicate_recovers_after_database_integrity_error(self):
        existing = LearningBehaviorEvent.objects.create(
            student=self.student, event_type='hint_requested', event_id='concurrent',
            metadata={'level': 1, 'shown': False},
        )
        matching = LearningBehaviorEvent.objects.filter(event_id='concurrent')
        # Simulate an insert winning the race after the initial lookup misses it.
        with patch.object(LearningBehaviorEvent.objects, 'filter', side_effect=[
            SimpleNamespace(first=lambda: None), matching,
        ]):
            event = record_learning_event(self.student, 'hint_requested',
                                          {'shown': False, 'level': 1},
                                          event_id='concurrent', strict=True)
        self.assertEqual(event.pk, existing.pk)
        self.assertEqual(LearningBehaviorEvent.objects.count(), 1)
