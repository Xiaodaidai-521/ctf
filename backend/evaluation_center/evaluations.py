"""Persisted OFFLINE evaluations; live gateway mode requires separate opt-in.

Only create_run / execute_run / interrupt_run require isolated test settings.
resolve_report is deliberately usable by module 7 in normal settings. A report
is an integrity-checked measurement of a registered narrow regression, not global
course acceptance, general model quality, or authority to change export policies.
"""
import hashlib
import json
import time
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .evaluation_fixtures import DATASET_VERSION, TASK_SCOPE, VIRTUAL_TIME, regression_cases
from .metrics import SOURCE_STATUS, metric
from .models import EvaluationCaseResult, EvaluationReport, EvaluationRun, NonFormalAccount

REPORT_VERSION = 'm8-report/1'
ENGINE_VERSION = 'm8-offline/1'
TEST_URLCONF = 'evaluation_center.test_urls'


class EvaluationError(ValueError):
    def __init__(self, message, code='evaluation_invalid'):
        super().__init__(message)
        self.code = code


def digest_of(value):
    try:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EvaluationError('评测材料必须是有限值 JSON。') from exc
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def require_isolated_write(actor):
    if (getattr(settings, 'EVALUATION_ISOLATED_TESTS', False) is not True or
            settings.ROOT_URLCONF != TEST_URLCONF):
        raise EvaluationError('评测写入仅允许显式隔离测试配置。', 'evaluation_not_isolated')
    from django.contrib.auth import get_user_model
    account = get_user_model().objects.filter(pk=getattr(actor, 'pk', None), is_active=True).first()
    if (not account or not (account.is_superuser or account.role == 'admin') or
            not NonFormalAccount.objects.filter(student=account, source='offline').exists()):
        raise EvaluationError('必须使用独立 offline 评测管理账号。', 'evaluation_account_required')
    return account


def _candidate_binding(candidate):
    from feedback_center.models import FeedbackCandidate
    try:
        candidate = FeedbackCandidate.objects.get(pk=candidate.pk, candidate_id=candidate.candidate_id)
    except (FeedbackCandidate.DoesNotExist, AttributeError, ValueError, ValidationError) as exc:
        raise EvaluationError('候选不存在。') from exc
    if not isinstance(candidate.baseline_config, dict) or not isinstance(candidate.candidate_config, dict):
        raise EvaluationError('候选配置必须是 JSON 对象。')
    baseline_digest = digest_of(candidate.baseline_config)
    candidate_digest = digest_of(candidate.candidate_config)
    if baseline_digest != candidate.baseline_config_digest or candidate_digest != candidate.config_digest:
        raise EvaluationError('候选配置内容与登记摘要不一致。')
    if not candidate.baseline_config_version or not candidate.candidate_config_version:
        raise EvaluationError('缺少配置版本。')
    return {
        'candidate_id': str(candidate.candidate_id),
        'baseline_config': deepcopy(candidate.baseline_config),
        'candidate_config': deepcopy(candidate.candidate_config),
        'baseline_config_digest': baseline_digest,
        'candidate_config_digest': candidate_digest,
        'baseline_config_version': candidate.baseline_config_version,
        'candidate_config_version': candidate.candidate_config_version,
        'single_changed_factor': candidate.single_changed_factor,
        'task_scope': deepcopy(candidate.target_task_versions),
        'excluded_scope': deepcopy(candidate.excluded_scope),
    }


def _code_versions():
    """Hash actual pure implementation files, not merely a caller's version label."""
    root = Path(__file__).resolve().parent.parent
    files = set()
    for directory in ('contracts', 'judgment', 'policies', 'features', 'baselines', 'experiments'):
        files.update((root / 'export_risk' / directory).rglob('*.py'))
    files.update(root / name for name in (
        'teaching_agent/permissions.py', 'learning_map/services/pathing.py',
        'learning_map/constants.py', 'evaluation_center/evaluation_fixtures.py',
        'evaluation_center/evaluations.py', 'evaluation_center/metrics.py',
        'evaluation_center/live_fixtures.py', 'evaluation_center/live_evaluations.py',
        'evaluation_center/gateway.py',
    ))
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def _support_issues(binding):
    issues = []
    if binding['task_scope'] != TASK_SCOPE or binding['excluded_scope']:
        issues.append('task_scope_not_covered')
    if binding['single_changed_factor'] != 'export_record_limit':
        issues.append('factor_requires_unavailable_live_evaluation')
    for arm in ('baseline_config', 'candidate_config'):
        config = binding[arm]
        if set(config) != {'export_record_limit'}:
            issues.append(f'{arm}_unsupported_configuration')
        limit = config.get('export_record_limit')
        if type(limit) is not int or not 1 <= limit <= 1000000:
            issues.append(f'{arm}_invalid_threshold')
    return issues


def create_run(candidate, *, actor, purpose='synthetic teaching-policy regression',
               max_cases=None, max_duration_ms=30000, dataset_version=DATASET_VERSION):
    if dataset_version != DATASET_VERSION:
        from . import live_evaluations, live_fixtures
        if dataset_version != live_fixtures.DATASET_VERSION:
            raise EvaluationError('评测集合未登记。')
        return live_evaluations.create_run(candidate, actor=actor, purpose=purpose,
                                           max_cases=max_cases, max_duration_ms=max_duration_ms)
    actor = require_isolated_write(actor)
    binding = _candidate_binding(candidate)
    cases = regression_cases()
    if max_cases is None:
        max_cases = len(cases)
    if type(max_cases) is not int or not 0 <= max_cases <= len(cases):
        raise EvaluationError('案例预算超出冻结集合。')
    if type(max_duration_ms) is not int or not 0 <= max_duration_ms <= 300000:
        raise EvaluationError('耗时预算必须在 0..300000ms 内。')
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 200:
        raise EvaluationError('评测目的必须为 1..200 字符。')
    unavailable = sorted(set(getattr(settings, 'EVALUATION_UNAVAILABLE_DEPENDENCIES', ())))
    if not set(unavailable) <= {'export_risk', 'teaching_rules'}:
        raise EvaluationError('未知隔离依赖标记。')
    run_id = uuid.uuid4()
    frozen = {
        'run_id': str(run_id), 'actor_id': actor.pk, 'source': 'offline',
        'purpose': purpose, 'stage': 'phase1_read_only', 'mode': 'deterministic_replay',
        'binding': binding, 'dataset_version': DATASET_VERSION,
        'versions': {
            'engine': ENGINE_VERSION, 'code': _code_versions(), 'dataset': DATASET_VERSION,
            'annotation': 'synthetic-rubric/1', 'catalog': 'synthetic-catalog/1',
            'event_dictionary': 'v1', 'basis_card': 'synthetic-threshold-120/1',
            'model': 'not_invoked', 'model_parameters': None, 'pricing': 'unknown', 'prompt': 'not_evaluated',
            'knowledge_base': 'not_connected', 'teaching_policy': 'frozen-fact-rules/1',
            'verifier': 'pure-program-assertions/1', 'tools': 'none',
            'task_scope': binding['task_scope'], 'tag': 'synthetic-tags/1',
            'retest_interval_days': int(getattr(settings, 'LEARNING_MAP_RETEST_INTERVAL_DAYS', 3)),
        },
        'environment': {'network': 'disabled', 'simulated': True, 'actual_sandbox': False,
                        'unavailable_dependencies': unavailable},
        'budget': {'max_cases': max_cases, 'max_duration_ms': max_duration_ms,
                   'max_provider_calls': 0, 'cost_limit': None, 'concurrency': 1, 'retries': 0},
        'support_issues': _support_issues(binding), 'cases': cases,
    }
    return EvaluationRun.objects.create(run_id=run_id, candidate=candidate, actor=actor,
                                        frozen=frozen, manifest_digest=digest_of(frozen))


def _validate_manifest(run):
    if isinstance(run.frozen, dict) and run.frozen.get('mode') == 'live_gateway':
        from .live_evaluations import validate_manifest
        try:
            return validate_manifest(run)
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise EvaluationError('真实评测冻结清单损坏。') from exc
    f = run.frozen
    if not isinstance(f, dict) or digest_of(f) != run.manifest_digest:
        raise EvaluationError('冻结 manifest 摘要不一致。')
    if (f.get('run_id') != str(run.run_id) or f.get('actor_id') != run.actor_id or
            f.get('source') != 'offline' or f.get('mode') != 'deterministic_replay' or
            f.get('dataset_version') != DATASET_VERSION or f.get('cases') != regression_cases()):
        raise EvaluationError('冻结运行身份或案例清单不一致。')
    binding = f.get('binding', {})
    if (binding.get('candidate_id') != str(run.candidate.candidate_id) or
            digest_of(binding.get('baseline_config')) != binding.get('baseline_config_digest') or
            digest_of(binding.get('candidate_config')) != binding.get('candidate_config_digest') or
            f.get('support_issues') != _support_issues(binding)):
        raise EvaluationError('冻结配置绑定损坏。')


def _execute_case(case, config, frozen):
    """Closed dispatch to existing pure functions. No DB writes or outbound I/O."""
    adapter, inputs = case['adapter'], case['input']
    if adapter == 'export_rule':
        from dataclasses import replace
        from export_risk.contracts import AuthorizationResult
        from export_risk.experiments.scenarios import unapproved_recipient
        from export_risk.judgment.hard_constraints import evaluate_hard_constraints
        from export_risk.judgment.fusion import fuse
        from export_risk.policies.catalog import Policy
        step = unapproved_recipient().steps[0]
        request = replace(step.request, record_count=inputs['records'], recipient_id='rc1')
        auth = step.authorization
        violation = inputs.get('violation')
        if violation == 'recipient':
            request = replace(request, recipient_id='synthetic-outsider')
        elif violation == 'scope':
            request = replace(request, scope=('synthetic-out-of-scope',))
        elif violation == 'subject':
            auth = replace(auth, subject_id='synthetic-other-subject')
        elif violation == 'forbidden':
            auth = replace(auth, result=AuthorizationResult.FORBIDDEN)
        hard = evaluate_hard_constraints(request, auth)
        if hard.triggered:
            return {'action': 'deny', 'reason_codes': list(hard.reason_codes), 'simulated': True}
        profile = replace(step.profile, categories=('synthetic-sensitive',)) if inputs.get('protected') else step.profile
        policy = Policy(version='m8-frozen-threshold/1', arm='A',
                        single_request_threshold=config['export_record_limit'])
        result = fuse(policy, request, profile, {})
        return {'action': result.action.value, 'reason_codes': list(result.reason_codes),
                'obligations': [o.type for o in result.obligations], 'simulated': True}
    if adapter == 'export_replay':
        from export_risk.experiments.replay import replay_arm
        from export_risk.experiments.scenarios import unapproved_recipient
        result = replay_arm(unapproved_recipient(), inputs['policy'])
        return {'actions': [o.action for o in result.outcomes], 'simulated': result.simulated}
    if adapter == 'teaching_material':
        from teaching_agent.permissions import material_permission
        context = SimpleNamespace(task=SimpleNamespace(materials_withdrawn=inputs['withdrawn']),
                                  hint_level=0, analysis_unlocked=inputs['analysis_unlocked'])
        decision = material_permission(material_type=inputs['material_type'], context=context)
        return {'allowed': decision.allowed, 'reason': decision.reason}
    if adapter == 'teaching_redaction':
        from teaching_agent.permissions import strip_sensitive_content
        return strip_sensitive_content(inputs)
    if adapter == 'teaching_fact':
        from learning_map.services.pathing import derive_state
        if int(getattr(settings, 'LEARNING_MAP_RETEST_INTERVAL_DAYS', 3)) != frozen['versions']['retest_interval_days']:
            raise EvaluationError('教学规则环境版本已变化。')
        fact = SimpleNamespace(**inputs, retest_of_attempt_id=None,
                               occurred_at=datetime.fromisoformat(VIRTUAL_TIME))
        state, reason, due = derive_state(fact)
        return {'state': state, 'reason': reason, 'retest_due_at': due.isoformat() if due else None}
    raise EvaluationError('不支持的服务端适配器。')


def _matches(output, expected):
    return isinstance(output, dict) and all(key in output and output[key] == value
                                            for key, value in expected.items())


def _case_payload(case, frozen, ordinal, elapsed_ms):
    dependency = 'export_risk' if case['adapter'].startswith('export_') else 'teaching_rules'
    unavailable = dependency in frozen['environment']['unavailable_dependencies']
    blockers = list(frozen['support_issues'])
    if unavailable:
        blockers.append(f'dependency_unavailable:{dependency}')
    arms = {}
    for arm in ('baseline', 'candidate'):
        if blockers:
            arms[arm] = {'status': 'insufficient', 'output': None, 'repeat_output': None,
                         'deterministic': None, 'issues': blockers}
        else:
            try:
                config = frozen['binding'][arm + '_config']
                output = _execute_case(case, config, frozen)
                repeat = _execute_case(case, config, frozen)
                stable = output == repeat
                arms[arm] = {'status': 'pass' if stable and _matches(output, case['expected']) else 'fail',
                             'output': output, 'repeat_output': repeat, 'deterministic': stable,
                             'issues': [] if stable else ['nondeterministic_replay']}
            except (KeyboardInterrupt, InterruptedError):
                raise
            except Exception as exc:
                # Never persist exception text: providers/URLs/secrets are not report material.
                arms[arm] = {'status': 'error', 'output': None, 'repeat_output': None,
                             'deterministic': None, 'issues': ['environment_error:' + type(exc).__name__]}
    return {'case_id': case['case_id'], 'ordinal': ordinal, 'case_digest': digest_of(case),
            'group': case['group'], 'critical': case['critical'], 'arms': arms,
            'elapsed_ms': elapsed_ms, 'tokens': None, 'cost': None, 'provider_calls': 0,
            'source': 'offline', 'simulated': True}


def execute_run(run, *, actor):
    require_isolated_write(actor)
    run = EvaluationRun.objects.select_related('candidate').get(pk=run.pk)
    _validate_manifest(run)
    live = run.frozen['mode'] == 'live_gateway'
    if live:
        from . import live_evaluations
        live_evaluations.require_live()
    if _candidate_binding(run.candidate) != run.frozen['binding']:
        raise EvaluationError('运行前候选配置已变更。')
    if run.frozen['versions']['code'] != _code_versions():
        raise EvaluationError('冻结代码依赖已经变化，不能复现。')
    if EvaluationRun.objects.filter(pk=run.pk, state='created').update(
            state='running', started_at=timezone.now()) != 1:
        raise EvaluationError('运行只能执行一次；中断后请创建新运行。')
    start = time.monotonic()
    stop_reason = ''
    try:
        for ordinal, case in enumerate(run.frozen['cases']):
            if ordinal >= run.frozen['budget']['max_cases']:
                stop_reason = 'case_budget_exhausted'
                break
            if (time.monotonic() - start) * 1000 >= run.frozen['budget']['max_duration_ms']:
                stop_reason = 'time_budget_exhausted'
                break
            case_start = time.monotonic()
            payload = (live_evaluations.case_payload(
                case, run.frozen, ordinal, start + run.frozen['budget']['max_duration_ms'] / 1000)
                if live else _case_payload(case, run.frozen, ordinal, 0))
            payload['elapsed_ms'] = round((time.monotonic() - case_start) * 1000, 3)
            with transaction.atomic():
                active = EvaluationRun.objects.select_for_update().get(pk=run.pk)
                if active.state != 'running':
                    raise EvaluationError('运行已被中断。')
                EvaluationCaseResult.objects.create(run=run, case_id=case['case_id'], ordinal=ordinal,
                                                    payload=payload, result_digest=digest_of(payload))
            if live and payload.get('abort_reason'):
                stop_reason = payload['abort_reason']
                break
            if (time.monotonic() - start) * 1000 > run.frozen['budget']['max_duration_ms']:
                stop_reason = 'time_budget_exhausted'
                break
    except (KeyboardInterrupt, InterruptedError):
        stop_reason = 'interrupted'
    except Exception:
        stop_reason = 'execution_error'
    return _finish_run(run, stop_reason=stop_reason)


def interrupt_run(run, *, actor):
    """Finalize a stopped worker's durable partial results; never resume as passed."""
    require_isolated_write(actor)
    return _finish_run(run, stop_reason='interrupted')


def _validated_rows(run):
    if run.frozen['mode'] == 'live_gateway':
        from .live_evaluations import validated_rows
        return validated_rows(run)
    rows = list(run.case_results.order_by('ordinal'))
    cases = run.frozen['cases']
    for row in rows:
        if row.ordinal >= len(cases):
            raise EvaluationError('逐例结果超出冻结清单。')
        case, payload = cases[row.ordinal], row.payload
        if (digest_of(payload) != row.result_digest or row.case_id != case['case_id'] or
                payload.get('case_id') != row.case_id or payload.get('ordinal') != row.ordinal or
                payload.get('case_digest') != digest_of(case) or payload.get('group') != case['group'] or
                payload.get('critical') != case['critical'] or payload.get('source') != 'offline' or
                payload.get('simulated') is not True or payload.get('provider_calls') != 0 or
                payload.get('tokens') is not None or payload.get('cost') is not None):
            raise EvaluationError('逐例结果完整性校验失败。')
        if set(payload.get('arms', {})) != {'baseline', 'candidate'}:
            raise EvaluationError('缺少基准或候选逐例结果。')
        for arm in payload['arms'].values():
            if arm.get('status') not in ('pass', 'fail', 'insufficient', 'error'):
                raise EvaluationError('非法逐例状态。')
            if arm['status'] in ('pass', 'fail'):
                stable = arm.get('output') == arm.get('repeat_output')
                passed = stable and _matches(arm.get('output'), case['expected'])
                if arm.get('deterministic') != stable or (arm['status'] == 'pass') != passed:
                    raise EvaluationError('逐例断言与记录状态不一致。')
            elif arm.get('output') is not None or not arm.get('issues'):
                raise EvaluationError('缺失证据被伪装成可用输出。')
    return rows


def _report_payload(run, rows, report_id):
    if run.frozen['mode'] == 'live_gateway':
        from .live_evaluations import report_payload
        return report_payload(run, rows, report_id)
    frozen, binding = run.frozen, run.frozen['binding']
    total = len(frozen['cases'])
    missing = total - len(rows)
    complete = run.state == 'completed' and not missing and not run.stop_reason
    statuses = [row.payload['arms']['candidate']['status'] for row in rows]
    recommendation = ('insufficient_evidence' if not complete or frozen['support_issues'] or
                      any(status in ('error', 'insufficient') for status in statuses) else
                      'fail' if 'fail' in statuses else 'pass')
    window = {'start': run.started_at.isoformat() if run.started_at else None,
              'end': run.finished_at.isoformat() if run.finished_at else None}
    versions = {key: value for key, value in frozen['versions'].items() if key != 'code'}

    def envelope(num, den, missing_count=0, **kwargs):
        return metric(num, den, missing_count, window=window, versions=versions, source='offline', **kwargs)

    metrics = {}
    for group in ('teaching_effectiveness', 'data_security'):
        expected_count = sum(case['group'] == group for case in frozen['cases'])
        group_rows = [row for row in rows if row.payload['group'] == group]
        observed = [row for row in group_rows if row.payload['arms']['candidate']['status'] in ('pass', 'fail')]
        environment_error = any(row.payload['arms']['candidate']['status'] == 'error' for row in group_rows)
        metrics[group] = {'regression_assertions': envelope(
            sum(row.payload['arms']['candidate']['status'] == 'pass' for row in observed),
            len(observed), expected_count - len(observed),
            status='environment_affected' if environment_error else None)}
    metrics['teaching_effectiveness']['real_learning_improvement'] = envelope(None, 0, status='not_evaluated')
    metrics['data_security']['actual_protection'] = envelope(None, 0, status='not_evaluated')
    metrics['agent_runtime'] = {
        'case_completion': envelope(len(rows), total, missing),
        'deterministic_replay': envelope(
            sum(row.payload['arms']['candidate']['deterministic'] is True for row in rows),
            sum(row.payload['arms']['candidate']['deterministic'] is not None for row in rows),
            missing + sum(row.payload['arms']['candidate']['deterministic'] is None for row in rows)),
        'elapsed_ms': envelope(sum(row.payload['elapsed_ms'] for row in rows), len(rows), missing),
        'tokens': envelope(None, 0, len(rows), status='not_evaluated'),
        'cost': envelope(None, 0, len(rows), status='not_evaluated'),
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
        'run_id': str(run.run_id), 'report_id': str(report_id), 'report_version': REPORT_VERSION,
        'manifest_digest': run.manifest_digest, 'candidate_id': binding['candidate_id'],
        # Stable evidence digest excludes per-run IDs, timestamps and measured latency.
        # report_digest still covers the ENTIRE report, including these observations.
        'replay_digest': digest_of({'binding': binding, 'versions': frozen['versions'],
                                    'cases': [{'case_digest': row.payload['case_digest'],
                                               'arms': row.payload['arms']} for row in rows]}),
        'dataset_version': frozen['dataset_version'], 'versions': frozen['versions'],
        'baseline_config_digest': binding['baseline_config_digest'],
        'candidate_config_digest': binding['candidate_config_digest'],
        'baseline_config_version': binding['baseline_config_version'],
        'candidate_config_version': binding['candidate_config_version'],
        'task_scope': binding['task_scope'], 'excluded_scope': binding['excluded_scope'],
        'single_changed_factor': binding['single_changed_factor'],
        'purpose': frozen['purpose'], 'stage': frozen['stage'], 'mode': frozen['mode'],
        'source': 'offline', 'simulated': True, 'actual_sandbox': False,
        'completed': complete, 'missing_cases': missing, 'expected_cases': total,
        'completed_cases': len(rows), 'stop_reason': run.stop_reason,
        'recommendation': recommendation, 'metrics': metrics, 'source_status': dict(SOURCE_STATUS),
        'improved_cases': improved, 'regressed_cases': regressed, 'new_failures': regressed,
        'failed_cases': failed, 'support_issues': frozen['support_issues'],
        'case_results': [{'case_id': row.case_id, 'result_digest': row.result_digest,
                          'result': row.payload} for row in rows],
        'budget': frozen['budget'], 'window': window, 'tokens': None, 'cost': None,
        'provider_calls': 0, 'repeat_count': 2, 'live_api_variation': None,
        'no_ai_acceptance': {'status': 'not_evaluated',
                             'reason': 'Pure replay does not exercise end-to-end outage/retry/save flows.'},
        'review': {'status': 'not_reviewed', 'opinion': None},
        'limitations': [
            'Synthetic regression only; not global phase-1 acceptance or production accuracy.',
            'Teaching cases check pure rules, not student learning gains or event persistence.',
            'Module 3/4/5 unconnected; actual protection and sandbox isolation not evaluated.',
            'No live models/prompts/KB comparison; replay cannot approve those changes.',
            'Not an independent final acceptance set; no source grades or production policies written.',
        ],
    }


@transaction.atomic
def _finish_run(run, *, stop_reason):
    run = EvaluationRun.objects.select_for_update().select_related('candidate').get(pk=run.pk)
    _validate_manifest(run)
    if EvaluationReport.objects.filter(run=run).exists():
        return validate_report(run.report)
    rows = _validated_rows(run)
    run.state = 'incomplete' if stop_reason or len(rows) != len(run.frozen['cases']) else 'completed'
    run.stop_reason = stop_reason or ('missing_cases' if run.state == 'incomplete' else '')
    run.finished_at = timezone.now()
    run.save(update_fields=['state', 'stop_reason', 'finished_at'])
    report_id = uuid.uuid4()
    payload = _report_payload(run, rows, report_id)
    report = EvaluationReport.objects.create(run=run, report_id=report_id, report_version=REPORT_VERSION,
                                             payload=payload, report_digest=digest_of(payload))
    return validate_report(report)


def validate_report(report):
    """Recompute configuration/manifest/case/report integrity, without write settings."""
    try:
        report = EvaluationReport.objects.select_related('run__candidate').get(pk=report.pk)
        run = report.run
        _validate_manifest(run)
        rows = _validated_rows(run)
        if (report.report_version != REPORT_VERSION or
                report.payload != _report_payload(run, rows, report.report_id) or
                digest_of(report.payload) != report.report_digest):
            raise EvaluationError('报告内容或摘要完整性校验失败。')
    except (KeyError, TypeError, AttributeError, ValidationError, EvaluationReport.DoesNotExist) as exc:
        raise EvaluationError('报告不存在或结构损坏。') from exc
    return report


def report_reference(report):
    report = validate_report(report)
    payload = report.payload
    return {**{key: payload[key] for key in (
        'run_id', 'report_id', 'report_version', 'recommendation', 'completed', 'missing_cases',
        'dataset_version', 'baseline_config_digest', 'candidate_config_digest',
    )}, 'report_digest': report.report_digest}


def resolve_report(candidate, supplied_ref):
    """M7 API: resolve an exact, complete canonical reference or raise EvaluationError.

    Fully measured fail/insufficient results are valid needs-revision evidence.
    Missing cases, interrupted runs, stale candidates and invented reports are not.
    Optional canonical/report fields are assertions, never caller overrides.
    """
    if not isinstance(supplied_ref, dict) or not all(supplied_ref.get(key) for key in (
            'run_id', 'report_id', 'report_digest')):
        raise EvaluationError('必须提供真实 run_id、report_id 与 report_digest。')
    try:
        report = EvaluationReport.objects.select_related('run__candidate').get(
            report_id=supplied_ref['report_id'], run__run_id=supplied_ref['run_id'])
    except (ValueError, TypeError, ValidationError, EvaluationReport.DoesNotExist) as exc:
        raise EvaluationError('评测运行或报告不存在。') from exc
    report = validate_report(report)
    if _candidate_binding(candidate) != report.run.frozen['binding']:
        raise EvaluationError('报告未绑定候选确切 UUID、配置内容、版本或任务范围。')
    canonical = report_reference(report)
    if not canonical['completed'] or canonical['missing_cases']:
        raise EvaluationError('未完成或缺例报告不能作为审批依据。')
    for key, value in supplied_ref.items():
        if key in ('attached_at', 'attached_by'):
            continue  # M7 owns audit metadata, not the report conclusion.
        expected = canonical.get(key, report.payload.get(key))
        if key not in canonical and key not in report.payload:
            raise EvaluationError('未知报告引用字段。')
        # JSON equality alone equates true with 1; compare canonical JSON hashes.
        if digest_of(value) != digest_of(expected):
            raise EvaluationError(f'报告引用字段与服务端记录不一致：{key}')
    return canonical
