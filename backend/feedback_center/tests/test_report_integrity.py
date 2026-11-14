"""The candidate workflow must resolve persisted module-8 evidence at every gate."""
from copy import deepcopy

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from evaluation_center.models import EvaluationReport
from evaluation_center.tests.factories import completed_report
from feedback_center import constants
from feedback_center.models import FeedbackCandidate
from feedback_center.services import candidates


@override_settings(FEEDBACK_PHASE3_ENABLED=True, FEEDBACK_PHASE3_RELEASE_ENABLED=True)
class CandidateReportIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_user(username='audit-report-owner', role='teacher')
        cls.approver = users.objects.create_user(username='audit-report-approver', role='teacher')
        cls.releaser = users.objects.create_user(username='audit-report-releaser', role='teacher')

    def setUp(self):
        self.candidate = FeedbackCandidate.objects.create(
            owner=self.owner, title='Audit report integrity',
            state=constants.CANDIDATE_PENDING_EVAL,
            baseline_config_version='cfg-v1', candidate_config_version='cfg-v2',
            single_changed_factor='export_record_limit',
            target_task_versions=['TASK-X@1.0.0'], rollback_version='cfg-v1',
            baseline_config={'export_record_limit': 100},
            candidate_config={'export_record_limit': 120},
            baseline_config_digest=candidates.digest_of({'export_record_limit': 100}),
            config_digest=candidates.digest_of({'export_record_limit': 120}),
        )

    def attach_real(self):
        self.reference = completed_report(self.candidate)
        candidates.attach_report(self.candidate, actor=self.owner, report=self.reference)

    def approve_real(self):
        self.attach_real()
        candidates.complete_evaluation(self.candidate, actor=self.owner)
        candidates.approve(self.candidate, approver=self.approver, scope='Synthetic audit',
            observation_window='7 days', rollback_condition='Any regression')

    def test_fabricated_report_without_candidate_digest_is_rejected(self):
        report = {'run_id': 'run-forged', 'report_id': 'report-forged',
            'report_version': 'v1', 'report_digest': 'f' * 64,
            'recommendation': 'pass', 'completed': True, 'missing_cases': 0}
        with self.assertRaises(candidates.CandidateError):
            candidates.attach_report(self.candidate, actor=self.owner, report=report)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.state, constants.CANDIDATE_PENDING_EVAL)
        self.assertEqual(self.candidate.evaluation_report_ref, {})

    def test_minimal_real_reference_is_canonicalized_by_server(self):
        reference = completed_report(self.candidate)
        minimal = {key: reference[key] for key in ('run_id', 'report_id', 'report_digest')}
        candidates.attach_report(self.candidate, actor=self.owner, report=minimal)
        for key, value in reference.items():
            self.assertEqual(self.candidate.evaluation_report_ref[key], value)

    def test_modified_real_report_conclusion_is_rejected(self):
        reference = completed_report(self.candidate)
        reference['recommendation'] = 'fail'
        with self.assertRaises(candidates.CandidateError):
            candidates.attach_report(self.candidate, actor=self.owner, report=reference)

    def test_http_minimal_reference_does_not_inject_default_assertions(self):
        reference = completed_report(self.candidate)
        client = APIClient()
        client.force_authenticate(self.owner)
        response = client.post(
            f'/api/feedback/teacher/phase3/candidates/{self.candidate.candidate_id}/report/',
            {key: reference[key] for key in ('run_id', 'report_id', 'report_digest')},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.evaluation_report_ref['candidate_config_digest'], self.candidate.config_digest)

    def test_complete_evaluation_rechecks_stored_report(self):
        self.attach_real()
        self.candidate.evaluation_report_ref['report_digest'] = 'f' * 64
        self.candidate.save(update_fields=['evaluation_report_ref'])
        with self.assertRaises(candidates.CandidateError):
            candidates.complete_evaluation(self.candidate, actor=self.owner)

    def test_approval_rechecks_persistent_report_existence(self):
        self.attach_real()
        candidates.complete_evaluation(self.candidate, actor=self.owner)
        EvaluationReport.objects.filter(report_id=self.reference['report_id']).delete()
        with self.assertRaises(candidates.CandidateError):
            candidates.approve(self.candidate, approver=self.approver, scope='Synthetic audit',
                observation_window='7 days', rollback_condition='Any regression')

    def test_activation_rechecks_task_scope(self):
        self.approve_real()
        self.candidate.target_task_versions = ['UNREVIEWED-TASK@1.0.0']
        self.candidate.save(update_fields=['target_task_versions'])
        with self.assertRaises(candidates.CandidateError):
            candidates.activate(self.candidate, operator=self.releaser,
                applicable_future_tasks=['UNREVIEWED-TASK@1.0.0'])

    def test_activation_rechecks_report_payload_integrity(self):
        self.approve_real()
        report = EvaluationReport.objects.get(report_id=self.reference['report_id'])
        payload = deepcopy(report.payload)
        payload['completed_cases'] += 1
        EvaluationReport.objects.filter(pk=report.pk).update(payload=payload)
        with self.assertRaises(candidates.CandidateError):
            candidates.activate(self.candidate, operator=self.releaser,
                applicable_future_tasks=['TASK-X@1.0.0'])

    def test_real_report_passes_every_gate(self):
        self.approve_real()
        candidates.activate(self.candidate, operator=self.releaser,
            applicable_future_tasks=['TASK-X@1.0.0'])
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.state, constants.CANDIDATE_OBSERVING)
