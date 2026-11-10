"""Security reproduction: forged module-8 report can advance a candidate.

This test demonstrates that the candidate approval chain does NOT verify
evaluation reports against the module-8 evaluation store. A completely
forged report (invented run_id/report_id, omitted candidate_config_digest,
arbitrary report_digest) is accepted all the way through
attach -> complete_evaluation -> approve -> activate.

There is no module-8 store to check against: evaluation_report_ref is just
a JSON field on FeedbackCandidate. Nothing in attach_report(), approve(),
or _approval_is_current() validates report_id/run_id/report_digest against
any persistent evaluation record.
"""

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from feedback_center import constants
from feedback_center.models import (
    FeedbackCandidate,
    FeedbackIssueGroup,
    FeedbackTicket,
)
from feedback_center.services import candidates, issue_groups
from users.models import CTFUser


PHASE3_ENABLED = override_settings(
    FEEDBACK_PHASE3_ENABLED=True,
    FEEDBACK_PHASE3_RELEASE_ENABLED=True,
)


def _make_confirmed_ticket(student, *, category=constants.CATEGORY_TEACHING,
                           issue_type='scoring_dispute', now=None,
                           status=constants.STATUS_CONFIRMED):
    if now is None:
        now = timezone.now()
    ticket = FeedbackTicket.objects.create(
        client_request_id=f'req-{uuid.uuid4().hex}',
        request_fingerprint='x' * 64,
        submitter=student,
        submitter_role=student.role,
        student=student,
        catalog=None,
        task=None,
        task_version='',
        attempt_ref=f'external-attempt-{uuid.uuid4().hex[:8]}',
        category=category,
        issue_type=issue_type,
        dispute='评分争议复现测试',
        status=status,
        dedup_key=f'dedup-{uuid.uuid4().hex}',
        missing_evidence=[],
    )
    # Set created_at explicitly (models as auto_now_add)
    FeedbackTicket.objects.filter(pk=ticket.pk).update(
        created_at=now - timedelta(days=1) if now else now
    )
    ticket.refresh_from_db()
    return ticket


@PHASE3_ENABLED
class ForgedReportAdvanceTests(TestCase):
    """Walk a candidate through the full life cycle using a forged report."""

    def setUp(self):
        self.owner = CTFUser.objects.create_user(
            username='rep-owner', password='Passw0rd!', role='teacher'
        )
        self.approver = CTFUser.objects.create_user(
            username='rep-approver', password='Passw0rd!', role='teacher'
        )
        self.releaser = CTFUser.objects.create_user(
            username='rep-release', password='Passw0rd!', role='teacher'
        )
        self.student = CTFUser.objects.create_user(
            username='rep-student', password='Passw0rd!', role='student'
        )
        now = timezone.now()
        self.ticket = _make_confirmed_ticket(self.student, now=now)
        self.group = issue_groups.create_group(
            actor=self.owner, title='复现问题组',
            category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute',
            window_start=now - timedelta(days=7),
            window_end=now + timedelta(days=1),
        )
        issue_groups.add_member(self.group, self.ticket, actor=self.owner)
        issue_groups.confirm_group(self.group, reviewer=self.owner)

    def _candidate(self):
        return candidates.create_candidate(
            actor=self.owner,
            title='T=100 -> T=120 (forged report repro)',
            issue_group_ids=[self.group.group_id],
            baseline_config_version='cfg-v1',
            candidate_config_version='cfg-v1-T120',
            single_changed_factor='export_record_limit',
            target_task_versions=['TASK-X@1.0.0'],
            baseline_config={'export_record_limit': 100},
            candidate_config={'export_record_limit': 120},
            rollback_version='cfg-v1',
        )

    # ------------------------------------------------------------------
    # Scenario A: omit candidate_config_digest entirely
    # (mirrors the default frontend behaviour — the digest field is
    #  optional in CandidateReportSerializer and the check is guarded by
    #  `if report.get('candidate_config_digest')`)
    # ------------------------------------------------------------------
    def test_forged_report_omitted_digest_advances_through_activate(self):
        """A report with NO candidate_config_digest passes every gate."""

        # Step 1 - create + submit
        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_PENDING_EVAL)

        # Step 2 - attach a fully forged report
        forged_report = {
            'run_id': f'run-forged-{uuid.uuid4().hex[:8]}',
            'report_id': f'report-forged-{uuid.uuid4().hex[:8]}',
            'report_version': 'v1',
            'report_digest': 'f' * 64,
            # candidate_config_digest intentionally OMITTED - no cross-check
            'recommendation': constants.REPORT_RECOMMENDATION_PASS,
            'completed': True,
            'missing_cases': 0,
        }
        candidate = candidates.attach_report(
            candidate, actor=self.owner, report=forged_report
        )
        candidate.refresh_from_db()
        # attach_report transitions pending_eval -> evaluating
        self.assertEqual(candidate.state, constants.CANDIDATE_EVALUATING)
        self.assertEqual(
            candidate.evaluation_report_ref['recommendation'],
            constants.REPORT_RECOMMENDATION_PASS,
        )
        # The forged report_id is now stored verbatim
        self.assertEqual(
            candidate.evaluation_report_ref['run_id'],
            forged_report['run_id'],
        )
        self.assertEqual(
            candidate.evaluation_report_ref['report_id'],
            forged_report['report_id'],
        )

        # Step 3 - complete evaluation (pass -> pending_approval)
        candidate = candidates.complete_evaluation(
            candidate, actor=self.owner
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_PENDING_APPROVAL)

        # Step 4 - approve
        candidate = candidates.approve(
            candidate,
            approver=self.approver,
            scope='合成案例',
            observation_window='14 days',
            rollback_condition='关键反例失败即回退',
        )
        candidate.refresh_from_db()
        self.assertEqual(
            candidate.state, constants.CANDIDATE_APPROVED_PENDING_RELEASE
        )
        # approve() stored the forged report_id and digest in the approval record
        self.assertEqual(
            candidate.approval['approved_report_id'],
            forged_report['report_id'],
        )
        self.assertEqual(
            candidate.approval['approved_report_digest'],
            'f' * 64,
        )

        # Step 5 - _approval_is_current() says the approval is still valid
        ok, reason = candidates._approval_is_current(candidate)
        self.assertTrue(ok, f'Approval should be current but: {reason}')

        # Step 6 - activate (release gate)
        candidate = candidates.activate(
            candidate,
            operator=self.releaser,
            applicable_future_tasks=['TASK-X@1.0.0'],
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_OBSERVING)
        self.assertEqual(
            candidate.activation['effective_config_digest'],
            candidate.config_digest,
        )

        # Summary assertion: the candidate is now OBSERVING (activated) with
        # a report that was never produced by any module-8 evaluation engine.
        self.assertNotEqual(
            candidate.state, constants.CANDIDATE_ROLLED_BACK
        )
        self.assertNotEqual(
            candidate.state, constants.CANDIDATE_WITHDRAWN
        )

    # ------------------------------------------------------------------
    # Scenario B: supply a WRONG candidate_config_digest that happens to
    # match by using the candidate's own value
    # (this is the exact pattern the frontend uses - it sets
    #  candidate_config_digest = candidate.config_digest)
    # ------------------------------------------------------------------
    def test_forged_report_self_supplied_digest_advances(self):
        """A report carrying the candidate's own config_digest is accepted."""

        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_PENDING_EVAL)

        # The frontend pattern: set candidate_config_digest to the candidate's
        # own config_digest, report_digest to arbitrary value, invented IDs.
        forged_report = {
            'run_id': f'run-frontend-{uuid.uuid4().hex[:8]}',
            'report_id': f'report-frontend-{uuid.uuid4().hex[:8]}',
            'report_version': 'v1',
            'report_digest': 'd' * 64,
            'candidate_config_digest': candidate.config_digest,
            'recommendation': constants.REPORT_RECOMMENDATION_PASS,
            'completed': True,
            'missing_cases': 0,
        }
        candidate = candidates.attach_report(
            candidate, actor=self.owner, report=forged_report
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_EVALUATING)

        candidate = candidates.complete_evaluation(
            candidate, actor=self.owner
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_PENDING_APPROVAL)

        candidate = candidates.approve(
            candidate,
            approver=self.approver,
            scope='合成案例',
            observation_window='7 days',
            rollback_condition='任意反例即回退',
        )
        candidate.refresh_from_db()
        self.assertEqual(
            candidate.state, constants.CANDIDATE_APPROVED_PENDING_RELEASE
        )

        candidate = candidates.activate(
            candidate,
            operator=self.releaser,
            applicable_future_tasks=['TASK-X@1.0.0'],
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_OBSERVING)

    # ------------------------------------------------------------------
    # Scenario C: mismatched candidate_config_digest IS caught - this
    # confirms the digest check exists but is only useful when provided.
    # ------------------------------------------------------------------
    def test_mismatched_digest_is_rejected(self):
        """A wrong candidate_config_digest is rejected at attach_report."""

        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        candidate.refresh_from_db()

        report = {
            'run_id': 'run-1',
            'report_id': 'report-1',
            'report_version': 'v1',
            'report_digest': 'a' * 64,
            'candidate_config_digest': 'WRONG' + '0' * 55,
            'recommendation': constants.REPORT_RECOMMENDATION_PASS,
            'completed': True,
            'missing_cases': 0,
        }
        with self.assertRaises(candidates.CandidateError) as ctx:
            candidates.attach_report(
                candidate, actor=self.owner, report=report
            )
        self.assertIn('配置摘要', str(ctx.exception))
