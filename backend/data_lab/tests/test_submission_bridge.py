"""The real HTTP handoff requires saved evidence and survives delivery faults."""
from unittest.mock import patch

from django.db import DatabaseError

from data_lab.submissions import deliver, submit
from learning_map.models import VerificationFact
from skill_review.models import ManualReviewTask, SubmissionSnapshot, VerificationResult
from skill_review.services.submissions import SubmissionError, create_submission

from .base import LabTestCase
from .flows import complete_evidence


class SubmissionBridgeTests(LabTestCase):
    def test_http_submission_and_retry_share_one_verified_snapshot(self):
        data = complete_evidence(self)
        url = f'/api/data-lab/attempts/{self.lab.attempt.attempt_id}/submissions/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['handoff_status'], 'delivered')
        self.assertEqual(response.data['program_status'], 'passed')
        self.assertEqual(response.data['overall_status'], 'pending_manual')
        repeated = self.client.post(url, data, format='json')
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(repeated.data['module6_id'], response.data['module6_id'])
        self.assertEqual(SubmissionSnapshot.objects.count(), 1)
        self.assertEqual(VerificationResult.objects.count(), 1)
        self.assertEqual(ManualReviewTask.objects.count(), 1)
        self.assertEqual(VerificationFact.objects.count(), 1)

    def test_module6_json_cannot_supply_context_or_replay_an_existing_key(self):
        saved = submit(self.student, self.lab.attempt.attempt_id, complete_evidence(self))
        submission = saved.module6
        response = self.client.post(
            f'/api/skill-review/attempts/{self.lab.attempt.attempt_id}/submit/',
            {'client_submission_id': submission.client_submission_id,
             'payload': submission.payload, 'data_lab_evidence': saved.snapshot}, format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(SubmissionSnapshot.objects.count(), 1)
        self.assertEqual(VerificationResult.objects.count(), 1)

        foreign = self.new_lab(self.other)
        foreign_saved = submit(self.other, foreign.attempt.attempt_id, complete_evidence(self, foreign))
        for context in (saved.snapshot, foreign_saved):
            with self.subTest(context=type(context).__name__), self.assertRaises(SubmissionError):
                create_submission(
                    student=self.student, attempt=self.lab.attempt,
                    client_submission_id='untrusted-context', payload=submission.payload,
                    data_lab_evidence=context,
                )
        with self.assertRaises(SubmissionError):
            create_submission(
                student=self.student, attempt=self.lab.attempt,
                client_submission_id='wrong-digest',
                payload={'evidence_id': str(saved.submission_id), 'content_digest': '0' * 64},
                data_lab_evidence=saved,
            )
        self.assertEqual(SubmissionSnapshot.objects.count(), 2)

    def test_verifier_fault_preserves_evidence_and_retry_runs_verification_once(self):
        data = complete_evidence(self)
        with patch('data_lab.verification.verify_submission', side_effect=RuntimeError('verifier unavailable')):
            saved = submit(self.student, self.lab.attempt.attempt_id, data)
        self.assertEqual(saved.status, 'pending')
        self.assertIsNone(saved.module6_id)
        self.assertEqual(SubmissionSnapshot.objects.count(), 0)
        self.assertEqual(VerificationFact.objects.count(), 0)
        with patch('data_lab.services.run_worker', side_effect=AssertionError('worker must not replay')) as worker:
            recovered = deliver(saved)
        worker.assert_not_called()
        self.assertEqual(recovered.status, 'delivered')
        self.assertEqual(recovered.content_digest, saved.content_digest)
        self.assertEqual(SubmissionSnapshot.objects.count(), 1)
        self.assertEqual(VerificationFact.objects.count(), 1)

    def test_module1_fault_retries_frozen_result_without_reverification(self):
        data = complete_evidence(self)
        with patch('learning_map.services.handoff.emit_event', side_effect=DatabaseError('module1 unavailable')):
            saved = submit(self.student, self.lab.attempt.attempt_id, data)
        self.assertEqual(saved.status, 'pending_handoff')
        self.assertEqual(saved.failure_code, 'MODULE1_PENDING')
        self.assertEqual(saved.module6.results.get().program_status, 'passed')
        self.assertEqual(VerificationFact.objects.count(), 0)
        with patch('data_lab.verification.verify_submission', side_effect=AssertionError('must not reverify')) as verify:
            recovered = deliver(saved)
            repeated = deliver(recovered)
        verify.assert_not_called()
        self.assertEqual(repeated.status, 'delivered')
        self.assertEqual(SubmissionSnapshot.objects.count(), 1)
        self.assertEqual(VerificationResult.objects.count(), 1)
        self.assertEqual(VerificationFact.objects.count(), 1)
