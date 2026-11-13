"""Persist real correction handoffs to prove bounded, idempotent event IDs."""
from django.test import TestCase

from learning_analytics.models import LearningEvent
from skill_review import constants
from skill_review.services import correction, handoff, submissions
from users.models import CTFUser
from .test_module6 import good_payload, make_attempt, make_capability, make_catalog, make_task


class CorrectionHandoffEventTests(TestCase):
    def test_correction_dispatch_ids_fit_and_retry_keeps_original_event(self):
        student = CTFUser.objects.create_user(username='handoff-audit-student', role='student')
        teacher = CTFUser.objects.create_user(username='handoff-audit-teacher', role='teacher')
        catalog = make_catalog()
        capability = make_capability(catalog)
        task = make_task(catalog, capability)
        attempt = make_attempt(task, student, catalog)
        submission, _ = submissions.create_submission(
            student=student, attempt=attempt, client_submission_id='handoff-audit', payload=good_payload())
        changed = correction.create_correction(
            submission=submission, actor=teacher, source=constants.CORRECTION_SOURCE_TEACHER,
            reason='synthetic audit correction',
            changes={'overall_status': constants.OVERALL_FAILED,
                     'independence': constants.INDEPENDENCE_ASSISTED,
                     'assistance_snapshot': {'level': 2, 'source': constants.ASSISTANCE_SOURCE_TEACHER,
                                             'shown': True}})
        raw_id = f'm6-dispatch-{changed.corrected_result.result_id}-{changed.corrected_result.revision}-{changed.correction_id}'
        self.assertGreater(len(raw_id), 64)
        # Delivery acknowledgements carry the number of M1 facts sent. Their
        # bounded IDs are opaque; do not depend on a retired readable prefix.
        events = LearningEvent.objects.filter(
            event_type='verification_result', metadata__module1_sent=1,
        )
        self.assertEqual(events.count(), 2)
        event = events.get(metadata__result_id=str(changed.corrected_result.result_id))
        self.assertLessEqual(len(event.event_id), 64)
        original_pk, original_metadata = event.pk, event.metadata
        handoff.dispatch_result(changed.corrected_result, correction=changed)
        self.assertEqual(events.count(), 2)
        event.refresh_from_db()
        self.assertEqual(event.pk, original_pk)
        self.assertEqual(event.metadata, original_metadata)

        second = correction.create_correction(
            submission=submission, actor=teacher, source=constants.CORRECTION_SOURCE_TEACHER,
            reason='second synthetic correction',
            changes={'overall_status': constants.OVERALL_PASSED})
        next_event = events.get(metadata__result_id=str(second.corrected_result.result_id))
        self.assertNotEqual(next_event.event_id, event.event_id)
        self.assertLessEqual(len(next_event.event_id), 64)
        self.assertEqual(events.count(), 3)
