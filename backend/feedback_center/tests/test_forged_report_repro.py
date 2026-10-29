"""Security regression for the original three forged-report reproductions.

The first two previously proved invented report IDs could advance through
activation; assertions are deliberately reversed now that module eight owns
persistent evaluation evidence. Copying the candidate digest is not evidence.
The third attack (wrong config digest) remains rejected. Legitimate fixtures
execute a real isolated module-eight run, rather than supplying a fake pass.
"""

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from feedback_center import constants
from feedback_center.models import FeedbackTicket
from feedback_center.services import candidates, issue_groups
from users.models import CTFUser


PHASE3_ENABLED = override_settings(
    FEEDBACK_PHASE3_ENABLED=True,
    FEEDBACK_PHASE3_RELEASE_ENABLED=True,
)


@PHASE3_ENABLED
class ForgedReportAdvanceTests(TestCase):
    def setUp(self):
        self.owner = CTFUser.objects.create_user(username='rep-owner', role='teacher')
        self.approver = CTFUser.objects.create_user(username='rep-approver', role='teacher')
        self.releaser = CTFUser.objects.create_user(username='rep-release', role='teacher')
        self.student = CTFUser.objects.create_user(username='rep-student', role='student')
        now = timezone.now()
        ticket = FeedbackTicket.objects.create(
            client_request_id=f'req-{uuid.uuid4().hex}', request_fingerprint='x' * 64,
            submitter=self.student, submitter_role='student', student=self.student,
            attempt_ref=f'external-attempt-{uuid.uuid4().hex[:8]}',
            category=constants.CATEGORY_TEACHING, issue_type='scoring_dispute',
            dispute='合成评分争议', status=constants.STATUS_CONFIRMED,
            dedup_key=f'dedup-{uuid.uuid4().hex}', missing_evidence=[],
        )
        self.group = issue_groups.create_group(
            actor=self.owner, title='复现问题组', category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute', window_start=now - timedelta(days=7),
            window_end=now + timedelta(days=1),
        )
        issue_groups.add_member(self.group, ticket, actor=self.owner)
        issue_groups.confirm_group(self.group, reviewer=self.owner)

    def _candidate(self):
        candidate = candidates.create_candidate(
            actor=self.owner, title='T=100 -> T=120 (forged report repro)',
            issue_group_ids=[self.group.group_id], baseline_config_version='cfg-v1',
            candidate_config_version='cfg-v1-T120', single_changed_factor='export_record_limit',
            target_task_versions=['TASK-X@1.0.0'], baseline_config={'export_record_limit': 100},
            candidate_config={'export_record_limit': 120}, rollback_version='cfg-v1',
        )
        return candidates.submit_for_evaluation(candidate, actor=self.owner)

    def _forged(self):
        return {'run_id': f'run-forged-{uuid.uuid4().hex}',
                'report_id': f'report-forged-{uuid.uuid4().hex}', 'report_version': 'v1',
                'report_digest': 'f' * 64, 'recommendation': 'pass',
                'completed': True, 'missing_cases': 0}

    def _assert_rejected(self, candidate, report):
        with self.assertRaises(candidates.CandidateError):
            candidates.attach_report(candidate, actor=self.owner, report=report)
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_PENDING_EVAL)
        self.assertFalse(candidate.evaluation_report_ref)
        with self.assertRaises(candidates.CandidateError):
            candidates.complete_evaluation(candidate, actor=self.owner)
        self.assertFalse(candidate.activation)

    def _real(self, candidate):
        from evaluation_center.tests.factories import completed_report

        return completed_report(candidate)

    def _approved(self):
        candidate = self._candidate()
        candidates.attach_report(candidate, actor=self.owner, report=self._real(candidate))
        candidates.complete_evaluation(candidate, actor=self.owner)
        candidates.approve(candidate, approver=self.approver, scope='合成案例',
                           observation_window='14 days', rollback_condition='关键反例即回退')
        return candidate

    def test_forged_report_omitted_digest_is_rejected(self):
        self._assert_rejected(self._candidate(), self._forged())

    def test_forged_report_self_supplied_digest_is_rejected(self):
        candidate = self._candidate()
        self._assert_rejected(candidate, {**self._forged(), 'candidate_config_digest': candidate.config_digest})

    def test_mismatched_digest_is_rejected(self):
        self._assert_rejected(self._candidate(), {**self._forged(), 'candidate_config_digest': 'WRONG' + '0' * 55})

    def test_real_completed_report_still_attaches_and_releases(self):
        candidate = self._approved()
        candidates.activate(candidate, operator=self.releaser, applicable_future_tasks=['TASK-X@1.0.0'])
        self.assertEqual(candidate.state, constants.CANDIDATE_OBSERVING)

    def test_http_forged_rejected_and_real_report_accepted(self):
        candidate = self._candidate()
        client = APIClient()
        client.force_authenticate(self.owner)
        path = f'/api/feedback/teacher/phase3/candidates/{candidate.candidate_id}/report/'
        response = client.post(path, self._forged(), format='json')
        self.assertEqual(response.status_code, 400, response.content)
        response = client.post(path, self._real(candidate), format='json')
        self.assertEqual(response.status_code, 200, response.content)
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_EVALUATING)

    def test_real_report_missing_or_forged_report_digest_rejected(self):
        candidate = self._candidate()
        report = self._real(candidate)
        for digest in ('', 'f' * 64):
            with self.subTest(digest=digest):
                self._assert_rejected(candidate, {**report, 'report_digest': digest})

    def test_real_report_cannot_be_reused_for_identical_other_candidate(self):
        original = self._candidate()
        report = self._real(original)
        self._assert_rejected(self._candidate(), report)

    def test_content_mutation_without_digest_update_rejected(self):
        candidate = self._candidate()
        report = self._real(candidate)
        candidate.candidate_config = {'export_record_limit': 1000}
        candidate.save(update_fields=['candidate_config'])
        self._assert_rejected(candidate, report)

    def test_scope_and_version_changes_invalidate_report(self):
        for field, value in [('candidate_config_version', 'untested-v2'),
                             ('baseline_config_version', 'untested-base'),
                             ('target_task_versions', ['OTHER@2.0'])]:
            with self.subTest(field=field):
                candidate = self._candidate()
                report = self._real(candidate)
                setattr(candidate, field, value)
                candidate.save(update_fields=[field])
                self._assert_rejected(candidate, report)

    def test_approval_revalidates_persisted_report_reference(self):
        candidate = self._candidate()
        candidates.attach_report(candidate, actor=self.owner, report=self._real(candidate))
        candidates.complete_evaluation(candidate, actor=self.owner)
        candidate.evaluation_report_ref['run_id'] = str(uuid.uuid4())
        candidate.save(update_fields=['evaluation_report_ref'])
        with self.assertRaises(candidates.CandidateError):
            candidates.approve(candidate, approver=self.approver, scope='s', observation_window='7d', rollback_condition='r')

    def test_release_revalidates_and_rejects_scope_expansion(self):
        candidate = self._approved()
        with self.assertRaises(candidates.CandidateError):
            candidates.activate(candidate, operator=self.releaser, applicable_future_tasks=['UNTESTED@1'])
        candidate.evaluation_report_ref['run_id'] = str(uuid.uuid4())
        candidate.save(update_fields=['evaluation_report_ref'])
        with self.assertRaises(candidates.CandidateError):
            candidates.activate(candidate, operator=self.releaser, applicable_future_tasks=[])
