"""Opt-in, bounded real gateway evaluations using the ordinary M8 record store.

Only the transport is live. Inputs are synthetic, judgments are exact assertions,
and a report is never evidence of real learning gains or production protection.
"""
import json
import time
import uuid
from copy import deepcopy

from django.conf import settings

from . import live_fixtures as fixtures
from .metrics import SOURCE_STATUS, metric
from .models import EvaluationRun

MODE = 'live_gateway'
REPEAT_COUNT = 2
ENGINE_VERSION = 'm8-live-gateway/1'
GATEWAY = 'http://127.0.0.1:8317/v1/chat/completions'


def _core():
    from . import evaluations
    return evaluations


def require_live():
    if getattr(settings, 'EVALUATION_LIVE_GATEWAY_ENABLED', False) is not True:
        raise _core().EvaluationError('真实网关评测未显式启用。', 'live_gateway_disabled')


def _check_binding(binding):
    core = _core()
    factor = binding['single_changed_factor']
    if factor not in fixtures.FACTORS or binding['task_scope'] != fixtures.TASK_SCOPE or binding['excluded_scope']:
        raise core.EvaluationError('真实评测因素或任务范围未登记。')
    baseline, candidate = (binding[key] for key in ('baseline_config', 'candidate_config'))
    expected_keys = {'model_id', 'prompt_version', 'temperature', 'max_tokens'}
    for config in (baseline, candidate):
        if (set(config) != expected_keys or config['model_id'] not in fixtures.MODELS or
                config['prompt_version'] not in fixtures.PROMPTS or
                type(config['temperature']) is not int or config['temperature'] != 0 or
                type(config['max_tokens']) is not int or config['max_tokens'] != 256):
            raise core.EvaluationError('只允许已登记的模型、提示和固定采样参数；不接受密钥或地址。')
    if {key for key in expected_keys if baseline[key] != candidate[key]} != {factor}:
        raise core.EvaluationError('基准与候选必须仅改变登记的单一因素。')


def create_run(candidate, *, actor, purpose, max_cases, max_duration_ms):
    core = _core()
    actor = core.require_isolated_write(actor)
    require_live()
    binding = core._candidate_binding(candidate)
    _check_binding(binding)
    cases = fixtures.regression_cases()
    max_cases = len(cases) if max_cases is None else max_cases
    if type(max_cases) is not int or not 0 <= max_cases <= len(cases):
        raise core.EvaluationError('案例预算超出固定真实评测集合。')
    if type(max_duration_ms) is not int or not 0 <= max_duration_ms <= 1800000:
        raise core.EvaluationError('真实批次预算必须在0..1800000ms内。')
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 200:
        raise core.EvaluationError('评测目的必须为1..200字符。')
    run_id = uuid.uuid4()
    frozen = {
        'run_id': str(run_id), 'actor_id': actor.pk, 'source': 'offline',
        'purpose': purpose, 'stage': 'phase1_read_only', 'mode': MODE,
        'binding': binding, 'dataset_version': fixtures.DATASET_VERSION,
        'cases': cases, 'support_issues': [],
        'versions': {
            'engine': ENGINE_VERSION, 'dataset': fixtures.DATASET_VERSION,
            'code': core._code_versions(), 'task_scope': fixtures.TASK_SCOPE,
            'tag': 'synthetic-export-labels/1', 'annotation': 'exact-action/1',
            'model': {arm: binding[arm + '_config']['model_id'] for arm in ('baseline', 'candidate')},
            'prompt': {arm: binding[arm + '_config']['prompt_version'] for arm in ('baseline', 'candidate')},
            'prompt_snapshots': {version: fixtures.PROMPTS[version] for version in sorted({
                binding['baseline_config']['prompt_version'], binding['candidate_config']['prompt_version']})},
            'model_parameters': {'temperature': 0, 'max_tokens': 256},
            'pricing': 'unknown', 'knowledge_base': 'not_connected', 'tools': 'none',
        },
        'environment': {'network': 'loopback_gateway_only', 'gateway': GATEWAY,
                        'simulated': False, 'input_source': 'synthetic', 'actual_sandbox': False},
        'budget': {'max_cases': max_cases, 'max_duration_ms': max_duration_ms,
                   'max_provider_calls': max_cases * 2 * REPEAT_COUNT * 3,
                   'max_output_tokens_per_response': 256, 'cost_limit': None,
                   'concurrency': 1, 'retries': 2, 'repeat_count': REPEAT_COUNT},
    }
    return EvaluationRun.objects.create(run_id=run_id, candidate=candidate, actor=actor,
                                        frozen=frozen, manifest_digest=core.digest_of(frozen))


def validate_manifest(run):
    core = _core()
    frozen = run.frozen
    if (core.digest_of(frozen) != run.manifest_digest or frozen['run_id'] != str(run.run_id) or
            frozen['actor_id'] != run.actor_id or frozen['source'] != 'offline' or
            frozen['mode'] != MODE or frozen['dataset_version'] != fixtures.DATASET_VERSION or
            frozen['cases'] != fixtures.regression_cases() or frozen['support_issues'] != [] or
            frozen['stage'] != 'phase1_read_only'):
        raise core.EvaluationError('真实评测冻结清单不一致。')
    binding = frozen['binding']
    _check_binding(binding)
    if (binding['candidate_id'] != str(run.candidate.candidate_id) or
            any(core.digest_of(binding[arm + '_config']) != binding[arm + '_config_digest']
                for arm in ('baseline', 'candidate'))):
        raise core.EvaluationError('真实评测配置绑定损坏。')
    versions = frozen['versions']
    expected_prompts = {binding[arm + '_config']['prompt_version'] for arm in ('baseline', 'candidate')}
    if (versions['engine'] != ENGINE_VERSION or versions['dataset'] != fixtures.DATASET_VERSION or
            versions['prompt_snapshots'] != {version: fixtures.PROMPTS[version] for version in expected_prompts} or
            versions['model_parameters'] != {'temperature': 0, 'max_tokens': 256} or
            versions['task_scope'] != fixtures.TASK_SCOPE or
            any(versions[key] != {arm: binding[arm + '_config'][field] for arm in ('baseline', 'candidate')}
                for key, field in (('model', 'model_id'), ('prompt', 'prompt_version')))):
        raise core.EvaluationError('真实评测提示/模型版本快照不一致。')
    budget = frozen['budget']
    if (type(budget['max_cases']) is not int or not 0 <= budget['max_cases'] <= len(frozen['cases']) or
            type(budget['max_duration_ms']) is not int or not 0 <= budget['max_duration_ms'] <= 1800000 or
            budget != {'max_cases': budget['max_cases'], 'max_duration_ms': budget['max_duration_ms'],
                       'max_provider_calls': budget['max_cases'] * 2 * REPEAT_COUNT * 3,
                       'max_output_tokens_per_response': 256, 'cost_limit': None,
                       'concurrency': 1, 'retries': 2, 'repeat_count': REPEAT_COUNT} or
            frozen['environment'] != {'network': 'loopback_gateway_only', 'gateway': GATEWAY,
                                      'simulated': False, 'input_source': 'synthetic', 'actual_sandbox': False}):
        raise core.EvaluationError('真实评测环境或预算不一致。')


def _arm_result(observations, expected):
    errors = any(row['status'] != 'ok' for row in observations)
    complete = len(observations) == REPEAT_COUNT
    outputs = [row['output'] for row in observations if row['status'] == 'ok']
    stable = outputs[0] == outputs[1] if len(outputs) == REPEAT_COUNT else None
    status = ('error' if errors else 'insufficient' if not complete or not stable else
              'pass' if all(output == expected for output in outputs) else 'fail')
    return {'status': status, 'observations': observations, 'deterministic': None,
            'observed_agreement': stable}


def _usage(observations):
    result = {}
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        known = [row['usage'][key] for row in observations if row['usage'][key] is not None]
        # A failed/retried attempt may have unreported billed tokens; do not fill zero.
        missing = sum(row['usage'][key] is None for row in observations)
        missing += sum(max(0, len(row['attempts']) - 1) for row in observations)
        result[key] = {'known_sum': sum(known) if known else None,
                       'reported_responses': len(known), 'missing_observations_or_attempts': missing,
                       'total': sum(known) if observations and not missing else None}
    return result


def case_payload(case, frozen, ordinal, deadline):
    from .gateway import call_completion
    require_live()
    core = _core()
    arms = {}
    abort = False
    for arm in ('baseline', 'candidate'):
        config = frozen['binding'][arm + '_config']
        observations = []
        for _ in range(REPEAT_COUNT):
            if abort or time.monotonic() >= deadline:
                break
            # No table, expected answer, identity, credentials, or other cases.
            messages = [{'role': 'system', 'content': frozen['versions']['prompt_snapshots'][config['prompt_version']]},
                        {'role': 'user', 'content': json.dumps(case['input'], sort_keys=True, separators=(',', ':'))}]
            observation = call_completion(config, messages, deadline=deadline)
            observations.append(observation)
            if any(attempt.get('http_status') in (401, 403) for attempt in observation['attempts']):
                abort = True
        arms[arm] = _arm_result(observations, case['expected'])
    observations = [row for arm in arms.values() for row in arm['observations']]
    usage = _usage(observations)
    return {'case_id': case['case_id'], 'ordinal': ordinal, 'case_digest': core.digest_of(case),
            'group': case['group'], 'critical': case['critical'], 'arms': arms, 'elapsed_ms': 0,
            'tokens': usage['total_tokens']['total'], 'usage': usage, 'cost': None,
            'provider_calls': sum(len(row['attempts']) for row in observations),
            'successful_provider_calls': sum(row['status'] == 'ok' for row in observations),
            'source': 'offline', 'simulated': False, 'input_source': 'synthetic',
            'abort_reason': 'gateway_authentication_failed' if abort else ''}


def _validate_observation(row):
    core = _core()
    if set(row) != {'status', 'output', 'usage', 'response_model', 'attempts', 'error'}:
        raise core.EvaluationError('真实调用记录字段不合法。')
    if row['status'] not in ('ok', 'error') or not isinstance(row['attempts'], list) or len(row['attempts']) > 3:
        raise core.EvaluationError('真实调用记录状态不合法。')
    if set(row['usage']) != {'prompt_tokens', 'completion_tokens', 'total_tokens'} or any(
            value is not None and (type(value) is not int or value < 0) for value in row['usage'].values()):
        raise core.EvaluationError('token观测值不合法。')
    for attempt in row['attempts']:
        if (set(attempt) != {'status', 'error', 'http_status', 'elapsed_ms'} or
                attempt['status'] not in ('ok', 'error') or
                type(attempt['elapsed_ms']) not in (int, float) or attempt['elapsed_ms'] < 0):
            raise core.EvaluationError('调用尝试审计不合法。')
    if row['status'] == 'ok':
        if (not row['attempts'] or row['attempts'][-1]['status'] != 'ok' or row['error'] is not None or
                not isinstance(row['output'], dict) or set(row['output']) != {'action'} or
                row['output']['action'] not in ('allow', 'require_approval', 'deny', 'mask')):
            raise core.EvaluationError('调用成功缺少规范化输出。')
    elif row['output'] is not None or not row['error']:
        raise core.EvaluationError('调用失败不得伪装为输出。')


def validated_rows(run):
    core = _core()
    rows = list(run.case_results.order_by('ordinal'))
    for row in rows:
        if row.ordinal < 0 or row.ordinal >= len(run.frozen['cases']):
            raise core.EvaluationError('真实逐例结果超出清单。')
        case, payload = run.frozen['cases'][row.ordinal], row.payload
        if (core.digest_of(payload) != row.result_digest or row.case_id != case['case_id'] or
                payload['case_id'] != row.case_id or payload['ordinal'] != row.ordinal or
                payload['case_digest'] != core.digest_of(case) or payload['group'] != case['group'] or
                payload['critical'] != case['critical'] or payload['source'] != 'offline' or
                payload['simulated'] is not False or payload['input_source'] != 'synthetic' or payload['cost'] is not None or
                set(payload['arms']) != {'baseline', 'candidate'}):
            raise core.EvaluationError('真实逐例结果完整性校验失败。')
        for arm in payload['arms'].values():
            if not isinstance(arm['observations'], list) or len(arm['observations']) > REPEAT_COUNT:
                raise core.EvaluationError('真实调用重复次数不合法。')
            for observation in arm['observations']:
                _validate_observation(observation)
            if arm != _arm_result(arm['observations'], case['expected']):
                raise core.EvaluationError('真实调用断言与记录状态不一致。')
        observations = [item for arm in payload['arms'].values() for item in arm['observations']]
        usage = _usage(observations)
        abort = any(attempt['http_status'] in (401, 403) for item in observations for attempt in item['attempts'])
        if (payload['usage'] != usage or payload['tokens'] != usage['total_tokens']['total'] or
                payload['provider_calls'] != sum(len(item['attempts']) for item in observations) or
                payload['successful_provider_calls'] != sum(item['status'] == 'ok' for item in observations) or
                payload['abort_reason'] != ('gateway_authentication_failed' if abort else '')):
            raise core.EvaluationError('真实调用计数/用量/终止原因不一致。')
    return rows


def report_payload(run, rows, report_id):
    core = _core()
    frozen, binding = run.frozen, run.frozen['binding']
    total, missing = len(frozen['cases']), len(frozen['cases']) - len(rows)
    complete = run.state == 'completed' and not missing and not run.stop_reason
    arms = [arm for row in rows for arm in row.payload['arms'].values()]
    statuses = [row.payload['arms']['candidate']['status'] for row in rows]
    recommendation = ('insufficient_evidence' if not complete or any(
        arm['status'] in ('error', 'insufficient') for arm in arms) else 'fail' if 'fail' in statuses else 'pass')
    window = {'start': run.started_at.isoformat() if run.started_at else None,
              'end': run.finished_at.isoformat() if run.finished_at else None}
    versions = {key: value for key, value in frozen['versions'].items() if key != 'code'}

    def envelope(num, den, missing_count=0, **kwargs):
        return metric(num, den, missing_count, window=window, versions=versions, source='offline', **kwargs)

    arm_metrics, usages = {}, {}
    all_observations = []
    for arm in ('baseline', 'candidate'):
        observed = [row for row in rows if row.payload['arms'][arm]['status'] in ('pass', 'fail')]
        arm_observations = [item for row in rows for item in row.payload['arms'][arm]['observations']]
        all_observations.extend(arm_observations)
        arm_metrics[arm] = envelope(sum(row.payload['arms'][arm]['status'] == 'pass' for row in observed),
                                   len(observed), total - len(observed),
                                   status='environment_affected' if any(row['status'] == 'error' for row in arm_observations) else None)
        usages[arm] = _usage(arm_observations)
    usage = _usage(all_observations)
    expected_observations = total * 2 * REPEAT_COUNT
    observed_count = len(all_observations)
    calls = sum(row.payload['provider_calls'] for row in rows)
    successful = sum(row.payload['successful_provider_calls'] for row in rows)
    token_missing = usage['total_tokens']['missing_observations_or_attempts'] + expected_observations - observed_count
    metrics = {
        'teaching_effectiveness': {'real_learning_improvement': envelope(None, 0, status='not_evaluated')},
        'data_security': {**{arm + '_assertions': value for arm, value in arm_metrics.items()},
                          'actual_protection': envelope(None, 0, status='not_evaluated')},
        'agent_runtime': {
            'case_completion': envelope(len(rows), total, missing),
            'successful_responses': envelope(successful, expected_observations, expected_observations - successful),
            'elapsed_ms': envelope(sum(row.payload['elapsed_ms'] for row in rows), len(rows), missing),
            'tokens': envelope(usage['total_tokens']['known_sum'], usage['total_tokens']['reported_responses'], token_missing),
            'cost': envelope(None, 0, calls, status='not_connected'),
        },
    }
    improved, regressed, failed = [], [], []
    for row in rows:
        base, cand = (row.payload['arms'][arm]['status'] for arm in ('baseline', 'candidate'))
        if base == 'fail' and cand == 'pass':
            improved.append(row.case_id)
        if base == 'pass' and cand == 'fail':
            regressed.append(row.case_id)
        if cand == 'fail':
            failed.append(row.case_id)
    return {
        'run_id': str(run.run_id), 'report_id': str(report_id), 'report_version': core.REPORT_VERSION,
        'manifest_digest': run.manifest_digest, 'candidate_id': binding['candidate_id'],
        'dataset_version': frozen['dataset_version'], 'versions': frozen['versions'],
        **{key: deepcopy(binding[key]) for key in ('baseline_config_digest', 'candidate_config_digest',
            'baseline_config_version', 'candidate_config_version', 'task_scope', 'excluded_scope', 'single_changed_factor')},
        'configuration_snapshots': {arm: deepcopy(binding[arm + '_config']) for arm in ('baseline', 'candidate')},
        'purpose': frozen['purpose'], 'stage': frozen['stage'], 'mode': MODE, 'source': 'offline',
        'simulated': False, 'input_source': 'synthetic', 'actual_sandbox': False,
        'completed': complete, 'missing_cases': missing, 'expected_cases': total, 'completed_cases': len(rows),
        'stop_reason': run.stop_reason, 'recommendation': recommendation, 'metrics': metrics,
        'source_status': dict(SOURCE_STATUS), 'arm_metrics': arm_metrics, 'usage_by_arm': usages,
        'usage': usage, 'tokens': usage['total_tokens']['total'] if not token_missing else None, 'cost': None,
        'provider_calls': calls, 'successful_provider_calls': successful, 'repeat_count': REPEAT_COUNT,
        'live_api_variation': {'observed_arms': sum(arm['observed_agreement'] is not None for arm in arms),
                               'disagreeing_arms': sum(arm['observed_agreement'] is False for arm in arms),
                               'missing_arms': total * 2 - sum(arm['observed_agreement'] is not None for arm in arms)},
        'replay_digest': None, 'support_issues': [], 'budget': frozen['budget'], 'window': window,
        'improved_cases': improved, 'regressed_cases': regressed, 'new_failures': regressed, 'failed_cases': failed,
        'case_results': [{'case_id': row.case_id, 'result_digest': row.result_digest, 'result': row.payload} for row in rows],
        'no_ai_acceptance': {'status': 'not_evaluated', 'reason': 'Live classification is not an outage-flow acceptance.'},
        'review': {'status': 'not_reviewed', 'opinion': None},
        'limitations': [
            'Real gateway requests with synthetic inputs, not real student data or production authorization.',
            'Two observations per arm are measurements, not deterministic replay or independent acceptance.',
            'Only registered model/prompt classification factors; no KB, retrieval, tools, or real learning measurement.',
            'Module 3/4/5 unconnected; no physical isolation or actual protection claim.',
            'Token values are provider-reported; unknown/retried usage and all costs remain missing.',
        ],
    }
