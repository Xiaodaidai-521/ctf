"""Phase-3 tests: issue groups, candidate state machine and dispute link.

The write gate is closed by default, so every test enables it explicitly with
``override_settings``.  Nothing here publishes a real teaching configuration:
activation only moves a synthetic candidate's own state.
"""

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from learning_map.models import CatalogVersion
from skill_review import constants as m6_constants
from skill_review.models import ScoreDispute
from skill_review.services import submissions as m6_submissions
from skill_review.tests.test_module6 import (
    good_payload,
    make_attempt,
    make_capability,
    make_catalog,
    make_task,
)
from users.models import CTFUser

from feedback_center import constants
from feedback_center.models import (
    FeedbackCandidate,
    FeedbackIssueGroup,
    FeedbackIssueGroupMember,
    FeedbackModule6DisputeLink,
    FeedbackTicket,
)
from feedback_center.services import candidates, issue_groups
from feedback_center.services import dispute_link


PHASE3 = override_settings(
    FEEDBACK_PHASE3_ENABLED=True,
    FEEDBACK_PHASE3_RELEASE_ENABLED=True,
)


def make_ticket(student, *, category=constants.CATEGORY_TEACHING,
                issue_type='scoring_dispute', status=constants.STATUS_CONFIRMED,
                dispute='解释题评分偏低', attempt=None, catalog=None, task=None,
                missing_evidence=None, created_at=None):
    ticket = FeedbackTicket.objects.create(
        client_request_id=f'req-{uuid.uuid4().hex}',
        request_fingerprint='x' * 64,
        submitter=student,
        submitter_role=student.role,
        student=student,
        catalog=catalog,
        task=task,
        task_version=task.version if task else '',
        attempt=attempt,
        category=category,
        issue_type=issue_type,
        dispute=dispute,
        status=status,
        dedup_key=f'dedup-{uuid.uuid4().hex}',
        missing_evidence=missing_evidence or [],
    )
    if created_at is not None:
        FeedbackTicket.objects.filter(pk=ticket.pk).update(created_at=created_at)
        ticket.refresh_from_db()
    return ticket


class IssueGroupTests(TestCase):
    def setUp(self):
        self.teacher = CTFUser.objects.create_user(username='t', password='Passw0rd!', role='teacher')
        self.student = CTFUser.objects.create_user(username='s', password='Passw0rd!', role='student')
        self.now = timezone.now()
        self.window_start = self.now - timedelta(days=7)
        self.window_end = self.now + timedelta(days=1)

    def _ticket(self, student, dispute='解释题评分偏低'):
        return make_ticket(
            student, dispute=dispute,
            created_at=self.now - timedelta(days=1),
        )

    def test_counts_deduplicate_same_attempt(self):
        ticket = self._ticket(self.student)
        duplicate = make_ticket(
            self.student, dispute=ticket.dispute, status=constants.STATUS_DUPLICATE,
        )
        duplicate.duplicate_of = ticket
        duplicate.save(update_fields=['duplicate_of'])

        group = issue_groups.create_group(
            actor=self.teacher,
            title='评分争议组',
            category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute',
            window_start=self.window_start,
            window_end=self.window_end,
        )
        counts = group.counts
        self.assertEqual(counts['included_feedback'], 1)
        self.assertEqual(counts['deduplicated_instances'], 1)

    def test_confirm_requires_member_decision_reason(self):
        ticket = self._ticket(self.student)
        group = issue_groups.create_group(
            actor=self.teacher, title='g', category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute', window_start=self.window_start,
            window_end=self.window_end,
        )
        issue_groups.add_member(group, ticket, actor=self.teacher, included=False, reason='')
        with self.assertRaises(issue_groups.IssueGroupError):
            issue_groups.confirm_group(group, reviewer=self.teacher)

    def test_confirm_rejects_unconfirmed_ticket(self):
        ticket = self._ticket(self.student)
        group = issue_groups.create_group(
            actor=self.teacher, title='g', category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute', window_start=self.window_start,
            window_end=self.window_end,
        )
        FeedbackTicket.objects.filter(pk=ticket.pk).update(status=constants.STATUS_PENDING_FACT_REVIEW)
        with self.assertRaises(issue_groups.IssueGroupError):
            issue_groups.confirm_group(group, reviewer=self.teacher)

    def test_confirm_snapshots_counts(self):
        self._ticket(self.student)
        group = issue_groups.create_group(
            actor=self.teacher, title='g', category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute', window_start=self.window_start,
            window_end=self.window_end,
        )
        confirmed = issue_groups.confirm_group(group, reviewer=self.teacher)
        self.assertEqual(confirmed.status, constants.ISSUE_GROUP_CONFIRMED)
        self.assertEqual(confirmed.reviewed_by_id, self.teacher.id)
        self.assertIn('deduplicated_instances', confirmed.counts)
        self.assertTrue(confirmed.events.filter(action=constants.ISSUE_GROUP_ACTION_CONFIRMED).exists())

    def test_split_keeps_history(self):
        first = self._ticket(self.student, dispute='争议一')
        second = self._ticket(self.student, dispute='争议二')
        group = issue_groups.create_group(
            actor=self.teacher, title='g', category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute', window_start=self.window_start,
            window_end=self.window_end,
        )
        issue_groups.confirm_group(group, reviewer=self.teacher)
        new_group = issue_groups.split_group(
            group, feedback_ids=[second.feedback_id], actor=self.teacher, title='拆出',
        )
        group.refresh_from_db()
        self.assertEqual(group.status, constants.ISSUE_GROUP_SUPERSEDED)
        self.assertEqual(new_group.supersedes_id, group.id)
        self.assertTrue(
            new_group.members.filter(ticket=second).exists()
        )
        self.assertFalse(
            group.members.filter(ticket=second).exists()
        )
        self.assertTrue(group.events.filter(action=constants.ISSUE_GROUP_ACTION_SPLIT).exists())

    def test_merge_rejects_different_versions(self):
        group_a = issue_groups.create_group(
            actor=self.teacher, title='a', category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute', window_start=self.window_start,
            window_end=self.window_end,
        )
        group_b = issue_groups.create_group(
            actor=self.teacher, title='b', category=constants.CATEGORY_TEACHING,
            issue_type='hint_ineffective', window_start=self.window_start,
            window_end=self.window_end,
        )
        with self.assertRaises(issue_groups.IssueGroupError):
            issue_groups.merge_groups([group_a, group_b], actor=self.teacher, title='合并')


@PHASE3
class CandidateStateMachineTests(TestCase):
    def setUp(self):
        self.owner = CTFUser.objects.create_user(username='owner', password='Passw0rd!', role='teacher')
        self.approver = CTFUser.objects.create_user(username='approver', password='Passw0rd!', role='teacher')
        self.releaser = CTFUser.objects.create_user(username='release', password='Passw0rd!', role='teacher')
        self.student = CTFUser.objects.create_user(username='s2', password='Passw0rd!', role='student')
        now = timezone.now()
        make_ticket(self.student, created_at=now - timedelta(days=1))
        self.group = issue_groups.create_group(
            actor=self.owner, title='g', category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute', window_start=now - timedelta(days=7),
            window_end=now + timedelta(days=1),
        )
        issue_groups.confirm_group(self.group, reviewer=self.owner)

    def _candidate(self):
        return candidates.create_candidate(
            actor=self.owner,
            title='T=100 -> T=120',
            issue_group_ids=[self.group.group_id],
            baseline_config_version='cfg-v1',
            candidate_config_version='cfg-v1-T120',
            single_changed_factor='export_record_limit',
            target_task_versions=['TASK-X@1.0.0'],
            baseline_config={'export_record_limit': 100},
            candidate_config={'export_record_limit': 120},
            rollback_version='cfg-v1',
        )

    def _pass_report(self, candidate):
        return {
            'run_id': 'run-1',
            'report_id': 'report-1',
            'report_version': 'v1',
            'report_digest': 'd' * 64,
            'recommendation': constants.REPORT_RECOMMENDATION_PASS,
            'completed': True,
            'missing_cases': 0,
            'candidate_config_digest': candidate.config_digest,
        }

    def test_candidate_rejects_unconfirmed_group(self):
        pending = issue_groups.create_group(
            actor=self.owner, title='pending', category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute', window_start=timezone.now() - timedelta(days=7),
            window_end=timezone.now() + timedelta(days=1),
        )
        with self.assertRaises(candidates.CandidateError):
            candidates.create_candidate(
                actor=self.owner, title='x', issue_group_ids=[pending.group_id],
                baseline_config_version='a', candidate_config_version='b',
                single_changed_factor='f', target_task_versions=[],
                baseline_config={}, candidate_config={'v': 1}, rollback_version='a',
            )

    def test_full_happy_path(self):
        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        candidates.attach_report(candidate, actor=self.owner, report=self._pass_report(candidate))
        candidates.complete_evaluation(candidate, actor=self.owner)
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_PENDING_APPROVAL)

        candidates.approve(
            candidate, approver=self.approver, scope='合成案例',
            observation_window='14 days', rollback_condition='关键反例失败即回退',
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_APPROVED_PENDING_RELEASE)

        candidates.activate(
            candidate, operator=self.releaser, applicable_future_tasks=['TASK-X@1.0.0'],
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_OBSERVING)
        self.assertTrue(candidate.activation['affects_future_tasks_only'])

        candidates.record_observation(
            candidate, actor=self.releaser, report_id='obs-1',
            new_failures=0, note='观察 14 天',
        )
        candidates.mark_stable(candidate, actor=self.releaser, note='无退化')
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_STABLE)

        candidates.rollback(
            candidate, operator=self.releaser, reason='发现关键反例失败',
            result=constants.ROLLBACK_SUCCESS,
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_ROLLED_BACK)
        self.assertEqual(candidate.rollback['to_version'], 'cfg-v1')

    def test_author_cannot_approve_own_candidate(self):
        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        candidates.attach_report(candidate, actor=self.owner, report=self._pass_report(candidate))
        candidates.complete_evaluation(candidate, actor=self.owner)
        with self.assertRaises(candidates.CandidateError):
            candidates.approve(
                candidate, approver=self.owner, scope='x',
                observation_window='7d', rollback_condition='y',
            )

    def test_report_without_pass_goes_to_revision(self):
        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        report = self._pass_report(candidate)
        report['recommendation'] = constants.REPORT_RECOMMENDATION_INSUFFICIENT
        candidates.attach_report(candidate, actor=self.owner, report=report)
        candidates.complete_evaluation(candidate, actor=self.owner)
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_NEEDS_REVISION)

    def test_incomplete_report_rejected(self):
        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        report = self._pass_report(candidate)
        report['completed'] = False
        with self.assertRaises(candidates.CandidateError):
            candidates.attach_report(candidate, actor=self.owner, report=report)

    def test_config_change_invalidates_approval(self):
        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        candidates.attach_report(candidate, actor=self.owner, report=self._pass_report(candidate))
        candidates.complete_evaluation(candidate, actor=self.owner)
        candidates.approve(
            candidate, approver=self.approver, scope='s',
            observation_window='7d', rollback_condition='r',
        )
        candidate.refresh_from_db()
        candidate.candidate_config = {'export_record_limit': 150}
        candidate.config_digest = candidates.digest_of(candidate.candidate_config)
        candidate.save(update_fields=['candidate_config', 'config_digest'])

        with self.assertRaises(candidates.CandidateError):
            candidates.activate(
                candidate, operator=self.releaser, applicable_future_tasks=[],
            )

    def test_approver_cannot_release(self):
        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        candidates.attach_report(candidate, actor=self.owner, report=self._pass_report(candidate))
        candidates.complete_evaluation(candidate, actor=self.owner)
        candidates.approve(
            candidate, approver=self.approver, scope='s',
            observation_window='7d', rollback_condition='r',
        )
        with self.assertRaises(candidates.CandidateError):
            candidates.activate(
                candidate, operator=self.approver, applicable_future_tasks=[],
            )

    def test_rollback_unknown_is_not_success(self):
        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        candidates.attach_report(candidate, actor=self.owner, report=self._pass_report(candidate))
        candidates.complete_evaluation(candidate, actor=self.owner)
        candidates.approve(
            candidate, approver=self.approver, scope='s',
            observation_window='7d', rollback_condition='r',
        )
        candidates.activate(candidate, operator=self.releaser, applicable_future_tasks=[])
        candidates.rollback(
            candidate, operator=self.releaser, reason='发布回应丢失',
            result=constants.ROLLBACK_UNKNOWN,
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, constants.CANDIDATE_OBSERVING)
        self.assertEqual(candidate.rollback['result'], constants.ROLLBACK_UNKNOWN)

    def test_mark_stable_rejects_insufficient_observation(self):
        candidate = self._candidate()
        candidates.submit_for_evaluation(candidate, actor=self.owner)
        candidates.attach_report(candidate, actor=self.owner, report=self._pass_report(candidate))
        candidates.complete_evaluation(candidate, actor=self.owner)
        candidates.approve(
            candidate, approver=self.approver, scope='s',
            observation_window='7d', rollback_condition='r',
        )
        candidates.activate(candidate, operator=self.releaser, applicable_future_tasks=[])
        candidates.record_observation(
            candidate, actor=self.releaser, status=constants.OBSERVATION_INSUFFICIENT,
        )
        with self.assertRaises(candidates.CandidateError):
            candidates.mark_stable(candidate, actor=self.releaser)


class Phase3GateTests(TestCase):
    def setUp(self):
        self.teacher = CTFUser.objects.create_user(username='gt', password='Passw0rd!', role='teacher')
        self.student = CTFUser.objects.create_user(username='gs', password='Passw0rd!', role='student')
        self.client = APIClient()

    @override_settings(FEEDBACK_PHASE3_ENABLED=False, FEEDBACK_PHASE3_RELEASE_ENABLED=False)
    def test_phase3_write_closed_by_default(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post('/api/feedback/teacher/phase3/issue-groups/', {
            'title': 'g',
            'category': constants.CATEGORY_TEACHING,
            'issue_type': 'scoring_dispute',
            'window_start': (timezone.now() - timedelta(days=1)).isoformat(),
            'window_end': timezone.now().isoformat(),
        }, format='json')
        # Group creation is read-side preparation, so it is allowed; candidate
        # publication is what must stay closed.
        self.assertIn(response.status_code, (201, 400))
        candidate = self.client.post('/api/feedback/teacher/phase3/candidates/', {
            'title': 'x',
            'issue_group_ids': ['00000000-0000-0000-0000-000000000000'],
            'baseline_config_version': 'a',
            'candidate_config_version': 'b',
            'single_changed_factor': 'f',
            'rollback_version': 'a',
        }, format='json')
        self.assertEqual(candidate.status_code, 409, candidate.content)
        self.assertEqual(candidate.data['code'], constants.PHASE3_WRITE_DISABLED)

    def test_status_endpoint_reports_closed_release(self):
        response = self.client.get('/api/feedback/status/')
        self.assertEqual(response.status_code, 200)
        payload = response.data
        self.assertFalse(payload.get('candidate_management_enabled', True))


class DisputeLinkTests(TestCase):
    def setUp(self):
        self.teacher = CTFUser.objects.create_user(username='dt', password='Passw0rd!', role='teacher')
        self.student = CTFUser.objects.create_user(username='ds', password='Passw0rd!', role='student')
        self.catalog = make_catalog()
        self.capability = make_capability(self.catalog)
        self.task = make_task(self.catalog, self.capability)
        self.attempt = make_attempt(self.task, self.student, self.catalog)
        submission, _ = m6_submissions.create_submission(
            student=self.student, attempt=self.attempt,
            client_submission_id='dispute-link-1', payload=good_payload(),
        )
        self.submission = submission
        self.ticket = make_ticket(
            self.student,
            status=constants.STATUS_CONFIRMED,
            attempt=self.attempt,
            catalog=self.catalog,
            task=self.task,
        )

    def test_open_dispute_creates_module6_record(self):
        link, created = dispute_link.open_dispute_for_ticket(self.ticket, actor=self.teacher)
        self.assertTrue(created)
        self.assertEqual(link.submission_id, self.submission.submission_id)
        self.assertTrue(ScoreDispute.objects.filter(dispute_id=link.dispute_id).exists())

    def test_sync_mirrors_status_without_changing_score(self):
        link, _ = dispute_link.open_dispute_for_ticket(self.ticket, actor=self.teacher)
        dispute = ScoreDispute.objects.get(dispute_id=link.dispute_id)
        result_before = self.submission.results.get(is_current=True).overall_status
        from skill_review.services import disputes as m6_disputes

        m6_disputes.resolve_dispute(
            dispute, teacher=self.teacher,
            status=m6_constants.DISPUTE_RESOLVED, resolution='维持原判',
        )
        link, changed = dispute_link.sync_dispute_status(link)
        self.assertTrue(changed)
        self.assertEqual(link.status_snapshot, m6_constants.DISPUTE_RESOLVED)
        self.assertEqual(
            self.submission.results.get(is_current=True).overall_status,
            result_before,
        )

    def test_non_scoring_feedback_cannot_link(self):
        ticket = make_ticket(
            self.student, issue_type='hint_ineffective', attempt=self.attempt,
            catalog=self.catalog, task=self.task,
        )
        with self.assertRaises(dispute_link.DisputeLinkError):
            dispute_link.open_dispute_for_ticket(ticket, actor=self.teacher)

    def test_no_submission_cannot_link(self):
        ticket = make_ticket(self.student, attempt=None)
        with self.assertRaises(dispute_link.DisputeLinkError):
            dispute_link.open_dispute_for_ticket(ticket, actor=self.teacher)
