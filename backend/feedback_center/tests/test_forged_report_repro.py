"""Regression: caller-created JSON is never evidence for candidate approval."""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from feedback_center import constants
from feedback_center.models import FeedbackCandidate
from feedback_center.services import candidates


@override_settings(FEEDBACK_PHASE3_ENABLED=True, FEEDBACK_PHASE3_RELEASE_ENABLED=True)
class ForgedReportRejectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username='forged-report-owner', role='teacher')

    def setUp(self):
        self.candidate = FeedbackCandidate.objects.create(
            owner=self.owner, title='Forged report regression',
            state=constants.CANDIDATE_PENDING_EVAL,
            baseline_config_version='cfg-v1', candidate_config_version='cfg-v2',
            single_changed_factor='export_record_limit',
            target_task_versions=['TASK-X@1.0.0'], rollback_version='cfg-v1',
            baseline_config={'export_record_limit': 100},
            candidate_config={'export_record_limit': 120},
            baseline_config_digest=candidates.digest_of({'export_record_limit': 100}),
            config_digest=candidates.digest_of({'export_record_limit': 120}),
        )

    def forged_report(self, **values):
        return {
            'run_id': str(uuid.uuid4()), 'report_id': str(uuid.uuid4()),
            'report_version': 'v1', 'report_digest': 'f' * 64,
            'recommendation': constants.REPORT_RECOMMENDATION_PASS,
            'completed': True, 'missing_cases': 0, **values,
        }

    def assert_rejected(self, report):
        with self.assertRaises(candidates.CandidateError):
            candidates.attach_report(self.candidate, actor=self.owner, report=report)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.state, constants.CANDIDATE_PENDING_EVAL)
        self.assertEqual(self.candidate.evaluation_report_ref, {})
        self.assertEqual(self.candidate.approval, {})
        self.assertEqual(self.candidate.activation, {})

    def test_forged_report_without_candidate_digest_is_rejected(self):
        self.assert_rejected(self.forged_report())

    def test_self_supplied_candidate_digest_does_not_make_report_trusted(self):
        self.assert_rejected(self.forged_report(candidate_config_digest=self.candidate.config_digest))

    def test_mismatched_candidate_digest_is_rejected(self):
        self.assert_rejected(self.forged_report(candidate_config_digest='0' * 64))
