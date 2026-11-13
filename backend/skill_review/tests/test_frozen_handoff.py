"""Real generic M6 facts retain their identity, atomicity and frozen content."""
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

from django.db import DatabaseError
from django.test import TestCase

from learning_analytics.models import LearningEvent
from learning_map.models import VerificationFact
from skill_review.models import DownstreamNotice, SubmissionSnapshot, VerificationResult
from skill_review.services.handoff import dispatch_result, retry_module1_notice
from skill_review.tests.test_module6 import make_attempt, make_capability, make_catalog, make_task, RETEST_VALIDATOR
from users.models import CTFUser


class GenericFrozenHandoffTests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='frozen-generic-student')
        self.catalog = make_catalog()
        self.capability = make_capability(self.catalog, stable_id='C' * 64)
        self.task = make_task(self.catalog, self.capability, validator=RETEST_VALIDATOR)
        attempt = make_attempt(self.task, self.student, self.catalog)
        submission = SubmissionSnapshot.objects.create(
            client_submission_id=str(uuid4()), attempt=attempt, student=self.student,
            task=self.task, catalog=self.catalog, task_version=self.task.version,
            sequence=1, payload={'synthetic': True}, payload_hash='a' * 64,
            first_effective=True, independence='independent',
        )
        self.result = VerificationResult.objects.create(
            submission=submission, attempt=attempt, student=self.student,
            task=self.task, catalog=self.catalog, overall_status='passed', independence='independent',
            program_status='passed', verifier_version='generic-synthetic-v1',
        )

    def test_long_ids_repeated_delivery_and_sent_retry_remain_idempotent(self):
        sent, notices = dispatch_result(self.result)
        self.assertTrue(sent, notices[0].last_error)
        frozen = deepcopy(notices[0].payload)
        self.assertEqual(frozen['source'], 'skill_review')
        self.assertTrue(dispatch_result(self.result)[0])
        retried = retry_module1_notice(notices[0])
        self.assertEqual(retried.attempts, 1)
        self.assertEqual(retried.payload, frozen)
        self.assertEqual(VerificationFact.objects.count(), 1)
        self.assertEqual(DownstreamNotice.objects.count(), 3)
        self.assertTrue(all(len(event.event_id) <= 64 for event in LearningEvent.objects.all()))
        self.assertLessEqual(len(VerificationFact.objects.get().fact_id), 56)

    def test_event_failure_rolls_back_facts_and_retry_preserves_original_outcome(self):
        with patch('skill_review.services.handoff.events.emit_event', side_effect=DatabaseError('synthetic outage')):
            sent, notices = dispatch_result(self.result)
        self.assertFalse(sent)
        self.assertFalse(VerificationFact.objects.exists())
        self.assertFalse(LearningEvent.objects.exists())
        frozen = deepcopy(notices[0].payload)
        self.result.overall_status = 'failed'
        self.result.save(update_fields=['overall_status'])
        recovered = retry_module1_notice(notices[0])
        self.assertEqual(recovered.status, 'sent', recovered.last_error)
        self.assertEqual(recovered.payload, frozen)
        self.assertEqual(VerificationFact.objects.get().outcome, 'passed')

    def test_revision_appends_without_replacing_previous_facts_and_notices(self):
        _, old_notices = dispatch_result(self.result)
        old = VerificationFact.objects.get()
        self.result.revision = 2
        self.result.overall_status = 'failed'
        self.result.save(update_fields=['revision', 'overall_status'])
        sent, new_notices = dispatch_result(self.result)
        self.assertTrue(sent, new_notices[0].last_error)
        self.assertNotEqual(old_notices[0].pk, new_notices[0].pk)
        self.assertEqual(DownstreamNotice.objects.count(), 6)
        old.refresh_from_db()
        self.assertEqual(old.outcome, 'passed')
        self.assertEqual(VerificationFact.objects.count(), 2)

    def test_changed_content_at_same_identity_is_rejected_and_frozen_payload_survives(self):
        _, notices = dispatch_result(self.result)
        frozen = deepcopy(notices[0].payload)
        self.result.submission.first_effective = False
        self.result.submission.save(update_fields=['first_effective'])
        sent, repeated = dispatch_result(self.result)
        self.assertFalse(sent)
        self.assertEqual(repeated[0].status, 'failed')
        self.assertEqual(repeated[0].payload, frozen)
        self.assertTrue(VerificationFact.objects.get().first_attempt)
