from unittest.mock import patch
from django.db import IntegrityError
from rest_framework.exceptions import NotFound
from django.utils import timezone
from data_lab.common import Conflict
from data_lab.models import EvidenceSubmission
from data_lab.submissions import submit, deliver, owned_submission, submission_dto
from data_lab.help import analysis, teacher_help
from skill_review.models import SubmissionSnapshot, VerificationResult, ManualReviewTask
from skill_review.services.submissions import create_submission, SubmissionError, assistance_snapshot
from learning_map.models import VerificationFact
from .base import LabTestCase
from .flows import complete_evidence


class SubmissionTests(LabTestCase):
    def test_real_module6_result_and_module1_ack_idempotent(self):
        data = complete_evidence(self)
        saved = submit(self.student, self.lab.attempt.attempt_id, data)
        self.assertEqual(saved.status, 'delivered', saved.failure_code)
        result = saved.module6.results.get(is_current=True)
        self.assertEqual(result.program_status, 'passed', result.program_result)
        self.assertEqual(result.overall_status, 'pending_manual')
        self.assertEqual(ManualReviewTask.objects.count(), 1)
        self.assertEqual(VerificationFact.objects.count(), 1)
        self.assertEqual(VerificationFact.objects.get().outcome, 'pending_review')
        original = result.program_result['original_detection']
        self.assertEqual((original['true_positive'], original['false_positive'], original['false_negative']), (8, 1, 2))
        again = submit(self.student, self.lab.attempt.attempt_id, data)
        self.assertEqual(again.pk, saved.pk)
        self.assertEqual(SubmissionSnapshot.objects.count(), 1)
        self.assertEqual(VerificationResult.objects.count(), 1)
        self.assertEqual(VerificationFact.objects.count(), 1)
        self.assertEqual(submission_dto(saved)['execution_status'], 'not_started')
        with self.assertRaises(Conflict):
            submit(self.student, self.lab.attempt.attempt_id, {**data, 'explanation': '不同内容'})
        with self.assertRaises(NotFound):
            owned_submission(self.other, saved.submission_id)

    def test_saved_evidence_survives_module6_event_failure(self):
        data = complete_evidence(self)
        with patch('skill_review.services.events.emit_event', side_effect=IntegrityError('event unavailable')):
            saved = submit(self.student, self.lab.attempt.attempt_id, data)
        self.assertEqual(saved.status, 'pending')
        self.assertIsNone(saved.module6_id)
        self.assertEqual(SubmissionSnapshot.objects.count(), 0)
        recovered = deliver(saved)
        self.assertEqual(recovered.status, 'delivered')
        self.assertEqual(EvidenceSubmission.objects.count(), 1)
        self.assertEqual(SubmissionSnapshot.objects.count(), 1)

    def test_evidence_event_failure_rolls_back_snapshot(self):
        data = complete_evidence(self)
        with patch('data_lab.submissions.emit', side_effect=IntegrityError('event unavailable')):
            with self.assertRaises(IntegrityError):
                submit(self.student, self.lab.attempt.attempt_id, data)
        self.assertEqual(EvidenceSubmission.objects.count(), 0)
        self.assertEqual(SubmissionSnapshot.objects.count(), 0)

    def test_client_cannot_replay_evidence_through_module6(self):
        data = complete_evidence(self)
        saved = submit(self.student, self.lab.attempt.attempt_id, data)
        with self.assertRaises(SubmissionError):
            create_submission(student=self.student, attempt=self.lab.attempt, client_submission_id='forged',
                payload={'evidence_id': str(saved.submission_id), 'content_digest': saved.content_digest})
        self.assertEqual(SubmissionSnapshot.objects.count(), 1)

    def test_foreign_replays_and_duplicate_variants_rejected(self):
        data = complete_evidence(self)
        with self.assertRaises(Conflict):
            submit(self.student, self.lab.attempt.attempt_id, {**data, 'replay_ids': [data['replay_ids'][0]] * 4})
        other = self.new_lab(self.other)
        other_data = complete_evidence(self, other)
        with self.assertRaises(Conflict):
            submit(self.student, self.lab.attempt.attempt_id, {**data, 'replay_ids': other_data['replay_ids']})

    def test_teacher_help_and_old_analysis_never_independent(self):
        teacher_help(self.teacher, self.lab.case, self.lab.attempt.attempt_id,
            {'summary': '提示区分业务事实', 'level': 1, 'idempotency_key': 'teacher'})
        saved = submit(self.student, self.lab.attempt.attempt_id, complete_evidence(self))
        self.assertEqual(saved.module6.independence, 'assisted')
        self.assertEqual(VerificationFact.objects.get().assistance_source, 'teacher')
        analysis(self.student, self.lab.attempt.attempt_id)
        fresh = self.new_lab()
        self.assertEqual(assistance_snapshot(attempt=fresh.attempt, before=timezone.now())['independence'], 'unknown')
        self.assertEqual(assistance_snapshot(attempt=fresh.attempt, before=timezone.now(), tracking='missing')['independence'], 'unknown')
