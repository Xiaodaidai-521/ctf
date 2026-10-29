import importlib
import uuid
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import Resolver404, clear_url_caches, get_resolver
from rest_framework.test import APIClient

from evaluation_center import evaluations
from evaluation_center.evaluation_fixtures import regression_cases
from evaluation_center.models import EvaluationCaseResult, EvaluationReport, EvaluationRun, NonFormalAccount
from evaluation_center.tests.factories import completed_report
from feedback_center.models import FeedbackCandidate


@override_settings(EVALUATION_ISOLATED_TESTS=True, ROOT_URLCONF='evaluation_center.test_urls',
                   EVALUATION_TEST_ADAPTER_ENABLED=True, EVALUATION_UNAVAILABLE_DEPENDENCIES=())
class EvaluationTests(TestCase):
    def setUp(self):
        # Full discovery can import test_urls before this isolated override.
        import evaluation_center.test_urls as test_urls
        importlib.reload(test_urls)
        clear_url_caches()
        self.admin = get_user_model().objects.create_user(username='offline-admin', role='admin')
        NonFormalAccount.objects.create(student=self.admin, source='offline')
        self.candidate = self.make_candidate()
        self.client = APIClient()

    def make_candidate(self, **values):
        defaults = {'owner': self.admin, 'title': 'Synthetic limit exercise',
                    'baseline_config_version': 'cfg-v1', 'candidate_config_version': 'cfg-v2',
                    'single_changed_factor': 'export_record_limit',
                    'target_task_versions': ['TASK-X@1.0.0'], 'rollback_version': 'cfg-v1',
                    'baseline_config': {'export_record_limit': 100},
                    'candidate_config': {'export_record_limit': 120}}
        defaults.update(values)
        defaults['baseline_config_digest'] = evaluations.digest_of(defaults['baseline_config'])
        defaults['config_digest'] = evaluations.digest_of(defaults['candidate_config'])
        return FeedbackCandidate.objects.create(**defaults)

    def run_report(self, candidate=None, **options):
        run = evaluations.create_run(candidate or self.candidate, actor=self.admin, **options)
        return evaluations.execute_run(run, actor=self.admin)

    def assert_invalid_reference(self, reference, candidate=None):
        with self.assertRaises(evaluations.EvaluationError):
            evaluations.resolve_report(candidate or self.candidate, reference)

    def test_persistent_run_freezes_server_cases_and_complete_report(self):
        report = self.run_report()
        reference = evaluations.resolve_report(self.candidate, evaluations.report_reference(report))
        self.assertEqual(reference['recommendation'], 'pass')
        self.assertTrue(reference['completed'])
        self.assertEqual(reference['missing_cases'], 0)
        run = EvaluationRun.objects.get(run_id=reference['run_id'])
        self.assertEqual(run.case_results.count(), len(regression_cases()))
        self.assertEqual(run.frozen['cases'], regression_cases())
        self.assertEqual(report.report_digest, evaluations.digest_of(report.payload))
        self.assertIn('export-volume-110', report.payload['improved_cases'])
        self.assertEqual(report.payload['regressed_cases'], [])
        self.assertNotIn('baseline_config', report.payload)
        self.assertNotIn('candidate_config', report.payload)
        self.assertEqual(len(report.payload['case_results']), len(regression_cases()))

    def test_real_rule_regression_cannot_be_forced_to_pass(self):
        candidate = self.make_candidate(candidate_config={'export_record_limit': 200})
        report = self.run_report(candidate)
        self.assertEqual(report.payload['recommendation'], 'fail')
        self.assertIn('export-volume-121', report.payload['new_failures'])
        self.assertEqual(evaluations.resolve_report(candidate, evaluations.report_reference(report))['recommendation'], 'fail')

    def test_three_metric_groups_envelopes_and_explicit_unavailable_sources(self):
        report = self.run_report()
        payload = report.payload
        self.assertEqual(set(payload['metrics']), {'teaching_effectiveness', 'data_security', 'agent_runtime'})
        for group in payload['metrics'].values():
            for value in group.values():
                self.assertTrue({'numerator', 'denominator', 'missing', 'window', 'versions', 'source'} <= set(value))
                self.assertEqual(value['source'], 'offline')
                self.assertEqual(value['versions']['task_scope'], ['TASK-X@1.0.0'])
        for key in ('module3', 'module4', 'module5'):
            self.assertEqual(payload['source_status'][key], 'not_connected')
        self.assertEqual(payload['source_status']['actual_protection'], 'not_evaluated')
        self.assertEqual(payload['no_ai_acceptance']['status'], 'not_evaluated')
        for name in ('cost', 'tokens', 'live_api_variation'):
            self.assertIsNone(payload[name])
        for name in ('cost', 'tokens'):
            self.assertIsNone(payload['metrics']['agent_runtime'][name]['numerator'])
        self.assertTrue(payload['simulated'])
        self.assertFalse(payload['actual_sandbox'])
        self.assertEqual(payload['versions']['model'], 'not_invoked')
        self.assertTrue(payload['versions']['code'])

    def test_same_frozen_replay_outputs_are_deterministic_without_network(self):
        with patch('socket.socket.connect', side_effect=AssertionError('network forbidden')), \
                patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            first, second = self.run_report(), self.run_report()
        for one, two in zip(first.payload['case_results'], second.payload['case_results']):
            self.assertEqual(one['result']['arms'], two['result']['arms'])
            for arm in one['result']['arms'].values():
                self.assertEqual(arm['output'], arm['repeat_output'])
                self.assertTrue(arm['deterministic'])
        self.assertEqual(first.payload['recommendation'], 'pass')
        self.assertEqual(first.payload['replay_digest'], second.payload['replay_digest'])
        self.assertNotEqual(first.report_id, second.report_id)

    def test_no_source_teaching_scores_profiles_or_policies_are_written(self):
        from django.apps import apps
        app_names = ('learning_map', 'skill_review', 'teaching_agent', 'learning_analytics', 'export_risk')
        models = [model for app in app_names for model in apps.get_app_config(app).get_models()]
        before = {model._meta.label: model.objects.count() for model in models}
        candidate_before = deepcopy(self.candidate.__dict__)
        self.run_report()
        self.assertEqual(before, {model._meta.label: model.objects.count() for model in models})
        self.candidate.refresh_from_db()
        for field in ('state', 'candidate_config', 'baseline_config', 'approval', 'activation'):
            self.assertEqual(getattr(self.candidate, field), candidate_before[field])

    def test_missing_run_report_or_digest_rejected(self):
        valid = evaluations.report_reference(self.run_report())
        for field in ('run_id', 'report_id', 'report_digest'):
            ref = dict(valid)
            ref.pop(field)
            self.assert_invalid_reference(ref)
        for value in ('', 'not-a-uuid', str(uuid.uuid4())):
            self.assert_invalid_reference({**valid, 'run_id': value})
            self.assert_invalid_reference({**valid, 'report_id': value})
        self.assert_invalid_reference({**valid, 'report_digest': self.candidate.config_digest})

    def test_minimal_reference_is_resolved_to_canonical_full_reference(self):
        reference = evaluations.report_reference(self.run_report())
        minimal = {key: reference[key] for key in ('run_id', 'report_id', 'report_digest')}
        self.assertEqual(evaluations.resolve_report(self.candidate, minimal), reference)
        self.assertEqual(evaluations.resolve_report(self.candidate, {
            **minimal, 'attached_at': 'M7 audit timestamp', 'attached_by': 99}), reference)

    def test_optional_assertions_cannot_override_canonical_values(self):
        reference = evaluations.report_reference(self.run_report())
        for field, value in (
            ('recommendation', 'insufficient_evidence'), ('completed', False), ('completed', 1),
            ('missing_cases', 1), ('dataset_version', 'forged'), ('report_version', 'forged'),
            ('baseline_config_digest', ''), ('candidate_config_digest', '0' * 64),
            ('candidate_config_version', 'stale'), ('unknown_override', 'pass'),
        ):
            with self.subTest(field=field, value=value):
                self.assert_invalid_reference({**reference, field: value})

    def test_exact_candidate_uuid_not_just_same_configuration(self):
        reference = evaluations.report_reference(self.run_report())
        self.assert_invalid_reference(reference, self.make_candidate())

    def test_config_content_tamper_without_digest_update_rejected_using_fresh_database(self):
        reference = evaluations.report_reference(self.run_report())
        FeedbackCandidate.objects.filter(pk=self.candidate.pk).update(candidate_config={'export_record_limit': 300})
        self.assert_invalid_reference(reference)  # deliberately pass a stale Python instance

    def test_baseline_content_tamper_without_digest_update_rejected(self):
        reference = evaluations.report_reference(self.run_report())
        FeedbackCandidate.objects.filter(pk=self.candidate.pk).update(baseline_config={'export_record_limit': 300})
        self.assert_invalid_reference(reference)

    def test_config_versions_scope_and_factor_exact_binding(self):
        reference = evaluations.report_reference(self.run_report())
        for field, value in (
            ('candidate_config_version', 'cfg-v3'), ('baseline_config_version', 'cfg-v0'),
            ('target_task_versions', ['TASK-Y@1.0.0']), ('excluded_scope', ['TASK-X@1.0.0']),
            ('single_changed_factor', 'model'),
        ):
            original = getattr(self.candidate, field)
            FeedbackCandidate.objects.filter(pk=self.candidate.pk).update(**{field: value})
            self.assert_invalid_reference(reference)
            FeedbackCandidate.objects.filter(pk=self.candidate.pk).update(**{field: original})

    def test_frozen_config_or_manifest_tampering_rejected(self):
        report = self.run_report()
        reference = evaluations.report_reference(report)
        frozen = deepcopy(report.run.frozen)
        frozen['binding']['candidate_config']['export_record_limit'] = 300
        EvaluationRun.objects.filter(pk=report.run_id).update(frozen=frozen)
        self.assert_invalid_reference(reference)

    def test_manifest_case_edit_even_with_recomputed_manifest_digest_rejected(self):
        report = self.run_report()
        reference = evaluations.report_reference(report)
        frozen = deepcopy(report.run.frozen)
        frozen['cases'][0]['expected']['action'] = 'deny'
        EvaluationRun.objects.filter(pk=report.run_id).update(frozen=frozen, manifest_digest=evaluations.digest_of(frozen))
        self.assert_invalid_reference(reference)

    def test_case_payload_tampering_rejected(self):
        report = self.run_report()
        reference = evaluations.report_reference(report)
        row = report.run.case_results.first()
        payload = deepcopy(row.payload)
        payload['arms']['candidate']['output']['action'] = 'deny'
        EvaluationCaseResult.objects.filter(pk=row.pk).update(payload=payload)
        self.assert_invalid_reference(reference)

    def test_case_digest_tampering_rejected(self):
        report = self.run_report()
        reference = evaluations.report_reference(report)
        row = report.run.case_results.first()
        EvaluationCaseResult.objects.filter(pk=row.pk).update(result_digest='f' * 64)
        self.assert_invalid_reference(reference)

    def test_deleted_case_after_report_rejected(self):
        report = self.run_report()
        reference = evaluations.report_reference(report)
        report.run.case_results.first().delete()
        self.assert_invalid_reference(reference)

    def test_complete_report_digest_covers_metrics_versions_and_review(self):
        report = self.run_report()
        reference = evaluations.report_reference(report)
        for field, value in (('metrics', {}), ('review', {'opinion': 'approved'}), ('versions', {})):
            payload = deepcopy(report.payload)
            payload[field] = value
            EvaluationReport.objects.filter(pk=report.pk).update(payload=payload)
            self.assert_invalid_reference(reference)
        EvaluationReport.objects.filter(pk=report.pk).update(payload=report.payload, report_digest='x' * 64)
        self.assert_invalid_reference(reference)

    def test_fake_pass_report_with_rehashed_report_digest_rejected(self):
        candidate = self.make_candidate(candidate_config={'export_record_limit': 200})
        report = self.run_report(candidate)
        payload = deepcopy(report.payload)
        payload['recommendation'] = 'pass'
        new_digest = evaluations.digest_of(payload)
        EvaluationReport.objects.filter(pk=report.pk).update(payload=payload, report_digest=new_digest)
        self.assert_invalid_reference({'run_id': str(report.run.run_id), 'report_id': str(report.report_id),
                                       'report_digest': new_digest}, candidate)

    def test_case_budget_exhausted_is_incomplete_and_never_approval_evidence(self):
        report = self.run_report(max_cases=2)
        self.assertFalse(report.payload['completed'])
        self.assertEqual(report.payload['completed_cases'], 2)
        self.assertEqual(report.payload['recommendation'], 'insufficient_evidence')
        self.assertEqual(report.payload['stop_reason'], 'case_budget_exhausted')
        self.assert_invalid_reference(evaluations.report_reference(report))

    def test_zero_case_and_time_budgets_cannot_pass(self):
        for options in ({'max_cases': 0}, {'max_duration_ms': 0}):
            report = self.run_report(**options)
            self.assertFalse(report.payload['completed'])
            self.assertEqual(report.payload['completed_cases'], 0)
            self.assertEqual(report.payload['recommendation'], 'insufficient_evidence')
            self.assert_invalid_reference(evaluations.report_reference(report))

    def test_elapsed_budget_enforced_not_just_recorded(self):
        with patch('evaluation_center.evaluations.time.monotonic', side_effect=[0, 1]):
            report = self.run_report(max_duration_ms=10)
        self.assertEqual(report.payload['stop_reason'], 'time_budget_exhausted')
        self.assertFalse(report.payload['completed'])

    def test_keyboard_interruption_persists_incomplete_report(self):
        with patch('evaluation_center.evaluations._execute_case', side_effect=KeyboardInterrupt):
            report = self.run_report()
        self.assertFalse(report.payload['completed'])
        self.assertEqual(report.payload['stop_reason'], 'interrupted')
        self.assert_invalid_reference(evaluations.report_reference(report))

    def test_interrupted_error_after_partial_work_keeps_durable_cases(self):
        original = evaluations._execute_case
        calls = 0

        def interrupt(case, config, frozen):
            nonlocal calls
            calls += 1
            if calls > 4:  # first case: two arms, each executed twice
                raise InterruptedError('worker stopped')
            return original(case, config, frozen)

        with patch('evaluation_center.evaluations._execute_case', side_effect=interrupt):
            report = self.run_report()
        self.assertEqual(report.payload['completed_cases'], 1)
        self.assertEqual(report.payload['stop_reason'], 'interrupted')
        self.assertFalse(report.payload['completed'])
        self.assert_invalid_reference(evaluations.report_reference(report))

    def test_nondeterministic_replay_is_not_pass(self):
        calls = 0

        def unstable(*args):
            nonlocal calls
            calls += 1
            return {'action': 'allow' if calls % 2 else 'deny'}

        with patch('evaluation_center.evaluations._execute_case', side_effect=unstable):
            report = self.run_report()
        self.assertEqual(report.payload['recommendation'], 'fail')
        value = report.payload['metrics']['agent_runtime']['deterministic_replay']
        self.assertEqual(value['numerator'], 0)
        self.assertEqual(value['denominator'], len(regression_cases()))

    def test_stopped_worker_can_be_finalized_not_resumed(self):
        run = evaluations.create_run(self.candidate, actor=self.admin)
        EvaluationRun.objects.filter(pk=run.pk).update(state='running')
        report = evaluations.interrupt_run(run, actor=self.admin)
        self.assertFalse(report.payload['completed'])
        with self.assertRaises(evaluations.EvaluationError):
            evaluations.execute_run(run, actor=self.admin)

    def test_reexecution_of_completed_run_rejected(self):
        report = self.run_report()
        with self.assertRaises(evaluations.EvaluationError):
            evaluations.execute_run(report.run, actor=self.admin)
        self.assertEqual(report.run.case_results.count(), len(regression_cases()))

    def test_model_prompt_kb_parameters_and_unsupported_scope_are_insufficient(self):
        for values in (
            {'single_changed_factor': 'model', 'candidate_config': {'model': 'new-model'}},
            {'single_changed_factor': 'prompt', 'candidate_config': {'prompt': 'new-prompt'}},
            {'single_changed_factor': 'knowledge_base', 'candidate_config': {'knowledge_base': 'kb-v2'}},
            {'candidate_config': {'export_record_limit': 120, 'temperature': 0.2}},
            {'target_task_versions': ['REAL-TASK@1.0.0']},
            {'target_task_versions': []},
            {'target_task_versions': ['TASK-X@1.0.0', 'TASK-Y@1.0.0']},
        ):
            with self.subTest(values=values):
                candidate = self.make_candidate(**values)
                report = self.run_report(candidate)
                self.assertTrue(report.payload['completed'])
                self.assertEqual(report.payload['missing_cases'], 0)
                self.assertEqual(evaluations.resolve_report(candidate, evaluations.report_reference(report))['recommendation'], 'insufficient_evidence')
                self.assertTrue(report.payload['support_issues'])

    def test_actual_dependency_error_produces_evidence_missing_not_zero_or_pass(self):
        with patch('evaluation_center.evaluations._execute_case', side_effect=ImportError('secret token should not leak')):
            report = self.run_report()
        self.assertTrue(report.payload['completed'])
        self.assertEqual(report.payload['recommendation'], 'insufficient_evidence')
        self.assertNotIn('secret token', str(report.payload))
        value = report.payload['metrics']['data_security']['regression_assertions']
        self.assertEqual(value['status'], 'environment_affected')
        self.assertGreater(value['missing'], 0)
        self.assertIsNone(value['value'])

    def test_fixture_uses_real_services_independent_account_and_keeps_binding(self):
        original = evaluations._candidate_binding(self.candidate)
        for recommendation in ('pass', 'insufficient_evidence'):
            reference = completed_report(self.candidate, recommendation=recommendation)
            self.assertEqual(reference['recommendation'], recommendation)
            self.assertTrue(reference['completed'])
            self.assertEqual(reference['missing_cases'], 0)
            run = EvaluationRun.objects.get(run_id=reference['run_id'])
            self.assertNotEqual(run.actor_id, self.candidate.owner_id)
            self.assertEqual(run.actor.role, 'admin')
            self.assertTrue(NonFormalAccount.objects.filter(student=run.actor, source='offline').exists())
            self.assertEqual(original, run.frozen['binding'])
            self.assertEqual(evaluations.resolve_report(self.candidate, reference), reference)

    def test_fixture_will_not_fabricate_pass_for_failing_candidate(self):
        candidate = self.make_candidate(candidate_config={'export_record_limit': 200})
        with self.assertRaises(AssertionError):
            completed_report(candidate)
        report = EvaluationReport.objects.get(run__candidate=candidate)
        self.assertEqual(report.payload['recommendation'], 'fail')

    def test_writes_require_explicit_isolated_root_and_existing_reports_do_not(self):
        report = self.run_report()
        reference = evaluations.report_reference(report)
        for overrides in (
            {'EVALUATION_ISOLATED_TESTS': False}, {'ROOT_URLCONF': 'ctf_backend.urls'},
        ):
            with override_settings(**overrides):
                self.assertEqual(evaluations.resolve_report(self.candidate, reference), reference)
                with self.assertRaises(evaluations.EvaluationError):
                    evaluations.create_run(self.candidate, actor=self.admin)
                with self.assertRaises(evaluations.EvaluationError):
                    evaluations.execute_run(report.run, actor=self.admin)
                with self.assertRaises(evaluations.EvaluationError):
                    evaluations.interrupt_run(report.run, actor=self.admin)

    def test_student_teacher_formal_admin_demo_and_inactive_cannot_run(self):
        for role, source, active in (
            ('student', None, True), ('student', 'offline', True), ('teacher', 'offline', True),
            ('admin', None, True), ('admin', 'demo', True), ('admin', 'offline', False),
        ):
            actor = get_user_model().objects.create_user(username=uuid.uuid4().hex, role=role, is_active=active)
            if source:
                NonFormalAccount.objects.create(student=actor, source=source)
            with self.assertRaises(evaluations.EvaluationError):
                evaluations.create_run(self.candidate, actor=actor)

    def test_actor_permission_is_reloaded_not_trusted_from_python_object(self):
        get_user_model().objects.filter(pk=self.admin.pk).update(role='student')
        with self.assertRaises(evaluations.EvaluationError):
            evaluations.create_run(self.candidate, actor=self.admin)

    def test_invalid_budgets_rejected_before_persisting(self):
        for options in ({'max_cases': -1}, {'max_cases': True}, {'max_duration_ms': -1},
                        {'max_duration_ms': 300001}, {'max_cases': 10000}):
            with self.assertRaises(evaluations.EvaluationError):
                evaluations.create_run(self.candidate, actor=self.admin, **options)
        self.assertEqual(EvaluationRun.objects.count(), 0)

    def test_changed_frozen_code_not_replayed(self):
        run = evaluations.create_run(self.candidate, actor=self.admin)
        with patch('evaluation_center.evaluations._code_versions', return_value={}):
            with self.assertRaises(evaluations.EvaluationError):
                evaluations.execute_run(run, actor=self.admin)

    def test_dedicated_http_read_permission_not_ordinary_teacher(self):
        report = self.run_report()
        path = f'/api/evaluation/reports/{report.report_id}/'
        self.assertIn(self.client.get(path).status_code, (401, 403))
        teacher = get_user_model().objects.create_user(username='teacher', role='teacher')
        self.client.force_authenticate(teacher)
        self.assertEqual(self.client.get(path).status_code, 403)
        permission = Permission.objects.get(content_type__app_label='evaluation_center', codename='manage_evaluation')
        teacher.user_permissions.add(permission)
        self.client.force_authenticate(get_user_model().objects.get(pk=teacher.pk))
        self.assertEqual(self.client.get(path).status_code, 200)
        student = get_user_model().objects.create_user(username='student', role='student')
        student.user_permissions.add(permission)
        self.client.force_authenticate(student)
        self.assertEqual(self.client.get(path).status_code, 403)

    def test_http_create_execute_real_report(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/evaluation/runs/', {'candidate_id': str(self.candidate.candidate_id)}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        response = self.client.post(f"/api/evaluation/runs/{response.data['run_id']}/execute/", {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['reference']['recommendation'], 'pass')

    def test_run_and_report_reads_do_not_expose_unsupported_config_secrets(self):
        candidate = self.make_candidate(candidate_config={'api_key': 'synthetic-not-a-real-secret'},
                                        single_changed_factor='model')
        report = self.run_report(candidate)
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/evaluation/runs/{report.run.run_id}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('synthetic-not-a-real-secret', str(response.data))
        self.assertNotIn('synthetic-not-a-real-secret', str(report.payload))
        self.assertIn('manifest_summary', response.data)

    def test_request_cannot_supply_case_input_role_or_target_url(self):
        self.client.force_authenticate(self.admin)
        for key in ('case_input', 'role', 'url', 'target_url', 'manifest', 'baseline_config', 'candidate_config'):
            response = self.client.post('/api/evaluation/runs/',
                                        {'candidate_id': str(self.candidate.candidate_id), key: 'untrusted'}, format='json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(EvaluationRun.objects.count(), 0)

    def test_adapter_requires_separate_constant_time_token_and_server_account(self):
        run = evaluations.create_run(self.candidate, actor=self.admin)
        data = {'run_id': str(run.run_id)}
        with override_settings(EVALUATION_SERVICE_TOKEN='synthetic-service-token',
                               EVALUATION_SERVICE_ACCOUNT_ID=self.admin.pk):
            self.assertEqual(self.client.post('/api/evaluation/adapter/', data, format='json').status_code, 401)
            self.client.credentials(HTTP_AUTHORIZATION='Evaluation wrong')
            self.assertEqual(self.client.post('/api/evaluation/adapter/', data, format='json').status_code, 401)
            self.client.credentials(HTTP_AUTHORIZATION='Evaluation synthetic-service-token')
            import secrets
            with patch('evaluation_center.evaluation_views.secrets.compare_digest', wraps=secrets.compare_digest) as compare:
                response = self.client.post('/api/evaluation/adapter/', data, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            compare.assert_called_once()
            self.assertEqual(response.data['reference']['recommendation'], 'pass')

    def test_adapter_never_borrows_formal_student_identity(self):
        student = get_user_model().objects.create_user(username='real-student', role='student')
        run = evaluations.create_run(self.candidate, actor=self.admin)
        with override_settings(EVALUATION_SERVICE_TOKEN='service-token', EVALUATION_SERVICE_ACCOUNT_ID=student.pk):
            self.client.credentials(HTTP_AUTHORIZATION='Evaluation service-token')
            response = self.client.post('/api/evaluation/adapter/', {'run_id': str(run.run_id)}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(run.case_results.count(), 0)

    def test_adapter_payload_rejects_case_role_and_url(self):
        run = evaluations.create_run(self.candidate, actor=self.admin)
        with override_settings(EVALUATION_SERVICE_TOKEN='service-token', EVALUATION_SERVICE_ACCOUNT_ID=self.admin.pk):
            self.client.credentials(HTTP_AUTHORIZATION='Evaluation service-token')
            for key in ('case', 'input', 'role', 'url', 'actor_id'):
                response = self.client.post('/api/evaluation/adapter/',
                    {'run_id': str(run.run_id), key: 'forged'}, format='json')
                self.assertEqual(response.status_code, 400)
        self.assertEqual(run.case_results.count(), 0)

    def test_adapter_cannot_be_enabled_by_flag_alone_in_normal_settings(self):
        with override_settings(ROOT_URLCONF='ctf_backend.urls', EVALUATION_SERVICE_TOKEN='service-token',
                               EVALUATION_SERVICE_ACCOUNT_ID=self.admin.pk):
            from evaluation_center.evaluation_views import EvaluationServiceAuthentication
            from rest_framework.exceptions import AuthenticationFailed
            from types import SimpleNamespace
            with self.assertRaises(AuthenticationFailed):
                EvaluationServiceAuthentication().authenticate(SimpleNamespace(
                    headers={'Authorization': 'Evaluation service-token'}))
        with self.assertRaises(Resolver404):
            get_resolver('evaluation_center.urls').resolve('/adapter/')
