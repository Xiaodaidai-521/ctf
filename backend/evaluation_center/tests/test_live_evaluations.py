"""Live-mode contract tests with a mocked provider, never billed API calls."""
import json
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from evaluation_center import evaluations, live_fixtures
from evaluation_center.models import EvaluationCaseResult, EvaluationReport, NonFormalAccount
from feedback_center import constants
from feedback_center.models import FeedbackCandidate
from feedback_center.services import candidates


def response(config, messages, *, deadline):
    inputs = json.loads(messages[1]['content'])
    action = ('deny' if inputs.get('violation') else 'mask' if inputs.get('protected') else
              'require_approval' if inputs['records'] > 120 else 'allow')
    return {'status': 'ok', 'output': {'action': action}, 'response_model': config['model_id'],
            'usage': {'prompt_tokens': 80, 'completion_tokens': 8, 'total_tokens': 88},
            'attempts': [{'status': 'ok', 'error': None, 'http_status': 200, 'elapsed_ms': 1.2}],
            'error': None}


@override_settings(EVALUATION_ISOLATED_TESTS=True, ROOT_URLCONF='evaluation_center.test_urls',
                   EVALUATION_LIVE_GATEWAY_ENABLED=True, FEEDBACK_PHASE3_ENABLED=True)
class LiveEvaluationTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username='offline-live-test', role='admin')
        NonFormalAccount.objects.create(student=self.actor, source='offline')
        self.candidate = self.make_candidate()

    def make_candidate(self, factor='prompt_version', **values):
        baseline, candidate = live_fixtures.configurations(factor)
        fields = {'owner': self.actor, 'title': 'Synthetic inputs / mocked transport',
                  'baseline_config_version': 'live-cfg/1', 'candidate_config_version': 'live-cfg/2',
                  'single_changed_factor': factor, 'target_task_versions': live_fixtures.TASK_SCOPE,
                  'rollback_version': 'live-cfg/1', 'baseline_config': baseline, 'candidate_config': candidate,
                  'state': constants.CANDIDATE_PENDING_EVAL}
        fields.update(values)
        fields['baseline_config_digest'] = evaluations.digest_of(fields['baseline_config'])
        fields['config_digest'] = evaluations.digest_of(fields['candidate_config'])
        return FeedbackCandidate.objects.create(**fields)

    def create_run(self, candidate=None, **options):
        return evaluations.create_run(candidate or self.candidate, actor=self.actor,
                                      dataset_version=live_fixtures.DATASET_VERSION, **options)

    def run_report(self, candidate=None, **options):
        with patch('evaluation_center.gateway.call_completion', side_effect=response):
            return evaluations.execute_run(self.create_run(candidate, **options), actor=self.actor)

    def test_frozen_live_mode_and_configuration_snapshots(self):
        run = self.create_run()
        self.assertEqual(run.frozen['cases'], live_fixtures.regression_cases())
        self.assertEqual(run.frozen['mode'], 'live_gateway')
        self.assertFalse(run.frozen['environment']['simulated'])
        self.assertEqual(run.frozen['environment']['input_source'], 'synthetic')
        self.assertEqual(run.frozen['budget']['max_provider_calls'], 72)
        self.assertNotIn('api_key', json.dumps(run.frozen))
        self.assertEqual(run.frozen['versions']['prompt_snapshots'], live_fixtures.PROMPTS)

    def test_complete_two_arm_measurements_persist_with_usage_and_minimal_input(self):
        run = self.create_run()
        with patch('evaluation_center.gateway.call_completion', side_effect=response) as provider:
            report = evaluations.execute_run(run, actor=self.actor)
        self.assertEqual(provider.call_count, 24)
        for call in provider.call_args_list:
            config, messages = call.args
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0]['content'], live_fixtures.PROMPTS[config['prompt_version']])
            self.assertIn(json.loads(messages[1]['content']), [case['input'] for case in live_fixtures.regression_cases()])
            self.assertNotIn('expected', messages[1]['content'])
        self.assertEqual(EvaluationCaseResult.objects.filter(run=run).count(), 6)
        self.assertEqual(EvaluationReport.objects.filter(run=run).count(), 1)
        self.assertEqual(report.payload['recommendation'], 'pass')
        self.assertEqual(report.payload['provider_calls'], 24)
        self.assertEqual(report.payload['tokens'], 2112)
        self.assertIsNone(report.payload['cost'])
        self.assertIsNone(report.payload['replay_digest'])
        self.assertEqual(report.payload['arm_metrics']['baseline']['value'], 1)
        self.assertEqual(report.payload['configuration_snapshots']['candidate'], self.candidate.candidate_config)
        self.assertEqual(report.payload['source_status']['module5'], 'not_connected')

    def test_model_factor_registered_separately_from_prompt_factor(self):
        report = self.run_report(self.make_candidate('model_id'))
        self.assertEqual(report.payload['single_changed_factor'], 'model_id')
        self.assertEqual(set(report.payload['versions']['model'].values()), set(live_fixtures.MODELS))

    def test_unknown_dataset_and_unregistered_or_multiple_factors_rejected(self):
        with self.assertRaises(evaluations.EvaluationError):
            evaluations.create_run(self.candidate, actor=self.actor, dataset_version='user-dataset')
        configs = deepcopy(self.candidate.candidate_config)
        for change in ({'model_id': 'arbitrary-model'}, {'endpoint': 'http://example.org'},
                       {'api_key': 'not-a-real-secret'}, {'max_tokens': 10000},
                       {'model_id': 'deepseek-v4.1'}, {'prompt_version': 'caller-prompt'}):
            with self.subTest(change=change):
                candidate = self.make_candidate(candidate_config={**configs, **change})
                with self.assertRaises(evaluations.EvaluationError):
                    self.create_run(candidate)

    @override_settings(EVALUATION_LIVE_GATEWAY_ENABLED=False)
    def test_live_mode_requires_separate_opt_in(self):
        with self.assertRaises(evaluations.EvaluationError):
            self.create_run()

    def test_execution_checks_opt_in_again(self):
        run = self.create_run()
        with override_settings(EVALUATION_LIVE_GATEWAY_ENABLED=False), self.assertRaises(evaluations.EvaluationError):
            evaluations.execute_run(run, actor=self.actor)
        run.refresh_from_db()
        self.assertEqual(run.state, 'created')

    def test_formal_actor_and_production_execution_denied(self):
        NonFormalAccount.objects.all().delete()
        with self.assertRaises(evaluations.EvaluationError):
            self.create_run()
        with override_settings(ROOT_URLCONF='ctf_backend.urls'), self.assertRaises(evaluations.EvaluationError):
            self.create_run()

    def test_read_validation_and_m7_attachment_do_not_require_live_configuration(self):
        report = self.run_report()
        with override_settings(EVALUATION_LIVE_GATEWAY_ENABLED=False, EVALUATION_ISOLATED_TESTS=False,
                               ROOT_URLCONF='ctf_backend.urls'):
            ref = evaluations.report_reference(report)
            candidates.attach_report(self.candidate, actor=self.actor, report=ref)
            candidates.complete_evaluation(self.candidate, actor=self.actor)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.state, constants.CANDIDATE_PENDING_APPROVAL)
        self.assertTrue(self.candidate.events.filter(action='report_attached').exists())
        self.assertEqual(self.candidate.activation, {})

    def test_realistic_failed_assertions_follow_m7_needs_revision(self):
        def wrong(config, messages, *, deadline):
            observed = response(config, messages, deadline=deadline)
            if config['prompt_version'].endswith('/v2'):
                observed['output'] = {'action': 'allow'}
            return observed
        with patch('evaluation_center.gateway.call_completion', side_effect=wrong):
            report = evaluations.execute_run(self.create_run(), actor=self.actor)
        self.assertEqual(report.payload['recommendation'], 'fail')
        self.assertEqual(report.payload['arm_metrics']['candidate']['numerator'], 2)
        self.assertEqual(report.payload['arm_metrics']['candidate']['denominator'], 6)
        candidates.attach_report(self.candidate, actor=self.actor, report=evaluations.report_reference(report))
        candidates.complete_evaluation(self.candidate, actor=self.actor)
        self.assertEqual(self.candidate.state, constants.CANDIDATE_NEEDS_REVISION)

    def test_auth_failure_stops_and_persists_incomplete_report_m7_rejects(self):
        error = {'status': 'error', 'output': None, 'response_model': None,
                 'usage': {'prompt_tokens': None, 'completion_tokens': None, 'total_tokens': None},
                 'attempts': [{'status': 'error', 'error': 'http_error', 'http_status': 401, 'elapsed_ms': 3}],
                 'error': 'http_error'}
        with patch('evaluation_center.gateway.call_completion', return_value=error) as provider:
            report = evaluations.execute_run(self.create_run(), actor=self.actor)
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(report.payload['provider_calls'], 1)
        self.assertEqual(report.payload['successful_provider_calls'], 0)
        self.assertEqual(report.payload['stop_reason'], 'gateway_authentication_failed')
        self.assertEqual(report.payload['missing_cases'], 5)
        self.assertEqual(report.payload['recommendation'], 'insufficient_evidence')
        self.assertIsNone(report.payload['tokens'])
        self.assertIsNone(report.payload['arm_metrics']['baseline']['value'])
        with self.assertRaises(candidates.CandidateError):
            candidates.attach_report(self.candidate, actor=self.actor, report=evaluations.report_reference(report))

    def test_baseline_errors_cannot_produce_pass_even_if_candidate_passes(self):
        def baseline_error(config, messages, *, deadline):
            observed = response(config, messages, deadline=deadline)
            if config['prompt_version'].endswith('/v1'):
                observed.update(status='error', output=None, error='invalid_response')
                observed['attempts'][0].update(status='error', error='invalid_response')
            return observed
        with patch('evaluation_center.gateway.call_completion', side_effect=baseline_error):
            report = evaluations.execute_run(self.create_run(), actor=self.actor)
        self.assertTrue(report.payload['completed'])
        self.assertEqual(report.payload['recommendation'], 'insufficient_evidence')

    def test_observed_variation_is_insufficient_not_deterministic(self):
        counter = 0
        def varying(config, messages, *, deadline):
            nonlocal counter
            observed = response(config, messages, deadline=deadline)
            counter += 1
            if counter == 1:
                observed['output'] = {'action': 'deny'}
            return observed
        with patch('evaluation_center.gateway.call_completion', side_effect=varying):
            report = evaluations.execute_run(self.create_run(), actor=self.actor)
        self.assertEqual(report.payload['recommendation'], 'insufficient_evidence')
        self.assertEqual(report.payload['live_api_variation']['disagreeing_arms'], 1)

    def test_missing_usage_and_retry_usage_remain_unknown(self):
        def unknown(config, messages, *, deadline):
            observed = response(config, messages, deadline=deadline)
            observed['usage']['total_tokens'] = None
            observed['attempts'].insert(0, {'status': 'error', 'error': 'http_error', 'http_status': 503, 'elapsed_ms': 2})
            return observed
        with patch('evaluation_center.gateway.call_completion', side_effect=unknown):
            report = evaluations.execute_run(self.create_run(), actor=self.actor)
        self.assertIsNone(report.payload['tokens'])
        self.assertIsNone(report.payload['usage']['total_tokens']['known_sum'])
        self.assertEqual(report.payload['provider_calls'], 48)
        self.assertIsNone(report.payload['usage']['prompt_tokens']['total'])
        self.assertEqual(report.payload['usage']['prompt_tokens']['known_sum'], 1920)

    def test_budget_and_interruption_cannot_be_pass(self):
        for options in ({'max_cases': 1}, {'max_duration_ms': 0}):
            with self.subTest(options=options):
                report = self.run_report(**options)
                self.assertEqual(report.payload['recommendation'], 'insufficient_evidence')
                with self.assertRaises(evaluations.EvaluationError):
                    evaluations.resolve_report(self.candidate, evaluations.report_reference(report))
        report = evaluations.interrupt_run(self.create_run(), actor=self.actor)
        self.assertFalse(report.payload['completed'])
        self.assertEqual(report.payload['provider_calls'], 0)

    def test_raw_config_changes_or_other_candidate_cannot_reuse_report(self):
        report = self.run_report()
        ref = evaluations.report_reference(report)
        with self.assertRaises(evaluations.EvaluationError):
            evaluations.resolve_report(self.make_candidate(), ref)
        FeedbackCandidate.objects.filter(pk=self.candidate.pk).update(candidate_config={})
        with self.assertRaises(evaluations.EvaluationError):
            evaluations.resolve_report(self.candidate, ref)

    def test_forged_report_and_rehashed_inconsistent_case_are_rejected(self):
        report = self.run_report()
        original = deepcopy(report.payload)
        report.payload['provider_calls'] = 999
        report.report_digest = evaluations.digest_of(report.payload)
        report.save()
        with self.assertRaises(evaluations.EvaluationError):
            evaluations.validate_report(report)
        report.payload = original
        report.report_digest = evaluations.digest_of(original)
        report.save()
        row = report.run.case_results.first()
        row.payload['arms']['candidate']['status'] = 'fail'
        row.result_digest = evaluations.digest_of(row.payload)
        row.save()
        with self.assertRaises(evaluations.EvaluationError):
            evaluations.validate_report(report)

    def test_prompt_snapshot_cannot_change_even_with_new_manifest_digest(self):
        run = self.create_run()
        run.frozen['versions']['prompt_snapshots']['export-classifier/v1'] = 'caller prompt'
        run.manifest_digest = evaluations.digest_of(run.frozen)
        run.save()
        with self.assertRaises(evaluations.EvaluationError):
            evaluations.execute_run(run, actor=self.actor)

    def test_api_only_selects_registered_dataset_not_inputs_or_roles(self):
        client = APIClient()
        client.force_authenticate(self.actor)
        payload = {'candidate_id': str(self.candidate.candidate_id), 'dataset_version': live_fixtures.DATASET_VERSION}
        self.assertEqual(client.post('/api/evaluation/runs/', payload, format='json').status_code, 201)
        for extra in ({'input': {}}, {'role': 'admin'}, {'url': 'http://example.org'}, {'api_key': 'not-real'}):
            self.assertEqual(client.post('/api/evaluation/runs/', {**payload, **extra}, format='json').status_code, 400)

    def test_source_models_and_candidate_release_state_are_unchanged(self):
        from django.apps import apps
        source_models = [model for app in ('learning_map', 'skill_review', 'teaching_agent', 'learning_analytics', 'export_risk')
                         for model in apps.get_app_config(app).get_models()]
        before = {model._meta.label: model.objects.count() for model in source_models}
        self.run_report()
        self.assertEqual(before, {model._meta.label: model.objects.count() for model in source_models})
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.state, constants.CANDIDATE_PENDING_EVAL)
        self.assertEqual(self.candidate.activation, {})

    def test_command_refuses_ordinary_test_or_business_database(self):
        with self.assertRaises(CommandError):
            call_command('run_live_evaluation')
