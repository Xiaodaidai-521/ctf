"""Regression tests for canonical skill-review event IDs."""

import hashlib

from django.test import TestCase

from learning_analytics.models import LearningEvent
from skill_review.services.events import emit_event
from users.models import CTFUser


class EventIdNormalizationTests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='event-student', role='student')

    def test_long_event_id_fits_field_and_preserves_prefix_and_digest(self):
        for event_id in ('x' * 65, 'm6-retest-result-' + 'x' * 96, 'm6-review-' + '复盘' * 48):
            with self.subTest(event_id=event_id):
                event, created = emit_event(
                    user=self.student, event_type='verification_result', event_id=event_id,
                )
                event.refresh_from_db()
                self.assertTrue(created)
                self.assertLessEqual(len(event.event_id), 64)
                digest = hashlib.sha256(event_id.encode('utf-8')).hexdigest()[:24]
                self.assertEqual(event.event_id, f'{event_id[:39]}-{digest}')

    def test_repeated_long_event_id_returns_original_event(self):
        event_id = 'm6-retest-result-' + 'x' * 96
        first, created = emit_event(
            user=self.student, event_type='verification_result', event_id=event_id,
            extra={'result_id': 'original'},
        )
        second, second_created = emit_event(
            user=self.student, event_type='verification_result', event_id=event_id,
            extra={'result_id': 'retry'},
        )
        self.assertTrue(created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.event_id, second.event_id)
        self.assertEqual(LearningEvent.objects.count(), 1)
        self.assertEqual(LearningEvent.objects.get().metadata['result_id'], 'original')

    def test_different_long_event_ids_with_shared_prefix_remain_distinct(self):
        prefix = 'm6-retest-result-' + 'x' * 94
        first, first_created = emit_event(
            user=self.student, event_type='verification_result', event_id=prefix + '-a',
        )
        second, second_created = emit_event(
            user=self.student, event_type='verification_result', event_id=prefix + '-b',
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first_created)
        self.assertTrue(second_created)
        self.assertEqual(first.event_id[:39], second.event_id[:39])
        self.assertNotEqual(first.event_id, second.event_id)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(LearningEvent.objects.count(), 2)

    def test_short_event_id_is_unchanged(self):
        for event_id in ('m6-review-short', 'x' * 63, 'x' * 64, '事' * 64):
            with self.subTest(event_id=event_id):
                event, created = emit_event(
                    user=self.student, event_type='verification_result', event_id=event_id,
                )
                event.refresh_from_db()
                self.assertTrue(created)
                self.assertEqual(event.event_id, event_id)
                duplicate, duplicate_created = emit_event(
                    user=self.student, event_type='verification_result', event_id=event_id,
                )
                self.assertFalse(duplicate_created)
                self.assertEqual(duplicate.pk, event.pk)
