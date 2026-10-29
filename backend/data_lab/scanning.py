"""Resource-bounded teaching adapter around the existing parser/rule engine."""
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from uuid import uuid5, UUID

from mainline1.classification import BusinessContext, RuleConfiguration, load_baseline
from mainline1.parsing import AssetRef, Cell, Limits, ParseResult, Scope, Selection, fingerprint, parse_table
from mainline1.rules import scan_rules
from .catalog import asset_bytes, case_spec


class ScanFailure(ValueError):
    pass


def configuration():
    value = load_baseline().data()
    value['baseline_version'] = 'demo-rules-v1'
    value['allowed_environments'] = ['test']
    policy = value['policy']
    policy.update(version='demo-policy-v1-draft', dictionary_version='demo-dictionary-v1',
                  ruleset_version='demo-rules-v1', review_policy_version='demo-review-v1')
    policy['categories'] = []
    value['rules'] = []
    for category, implementation in [('DEMO_PERSON_REF', 'demo_person_ref_v1'), ('DEMO_CONTACT', 'demo_contact_v1')]:
        rule_id = 'teaching.' + implementation
        policy['categories'].append(dict(category_id=category,
            definition='合成形态候选；不是法律属性或真实等级结论', aliases=[], positive_examples=[],
            negative_examples=[], rule_refs=[rule_id], related_categories=[], protection_level='L2',
            review_conditions=['SYNTHETIC_REQUIRES_FACTS']))
        value['rules'].append(dict(rule_id=rule_id, version='1', implementation=implementation,
                                   category_id=category, enabled=True))
    policy['rule_refs'] = [r['rule_id'] for r in value['rules']]
    policy['content_hash'] = fingerprint({k: v for k, v in policy.items() if k != 'content_hash'})
    return RuleConfiguration.load(value)


def restore_parsed(value):
    data = dict(value)
    scope = data['scope']
    data['scope'] = Scope(scope['asset_version_id'], tuple(
        Selection(s['sheet_id'], tuple(map(tuple, s['rows'])), tuple(map(tuple, s['columns'])))
        for s in scope['selections']), scope['include_header'])
    data['cells'] = tuple(Cell(**cell) for cell in data['cells'])
    data['warnings'] = tuple(data['warnings'])
    data['excluded_contents'] = tuple(data['excluded_contents'])
    return ParseResult(**data)


def scan_registered(request):
    spec = case_spec(request['task_key'])
    raw = asset_bytes(request['task_key'])
    asset = AssetRef(request['asset_version_id'], request['domain'], 'sha256:' + spec['sha256'],
                     'csv', len(raw), 'private:data-lab:' + spec['fixture_id'])
    parsed = parse_table(raw, asset, limits=Limits(max_bytes=65536, max_rows=32, max_columns=8,
        max_cells=256, max_cell_codepoints=2048, max_seconds=3))
    meta = dict(schema_version='mainline1.proposed.v1', trace_id=request['scan_id'],
                environment='test', evaluation_run_id=None, domain_id=request['domain'],
                created_at=request['created_at'])
    context = BusinessContext.create(meta=meta, context_id=str(uuid5(UUID(request['scan_id']), 'context')),
        version=1, asset_version_id=parsed.asset_version_id, scope_hash=parsed.scope_hash,
        scenario=spec['title'], purpose=spec['facts']['F-PURPOSE'], table_description='登记合成教学材料；待教师签收')
    result = scan_rules(parsed, configuration(), context, meta=meta,
        asset=dict(asset_id=request['asset_id'], asset_version_id=parsed.asset_version_id,
                   content_hash=parsed.input_content_hash), principal=str(request['actor_id']),
        scan_id=request['scan_id'], applicability_ref=str(uuid5(UUID(request['scan_id']), 'applicability')),
        parsed_ref='private:data-lab:scan:' + request['scan_id'], semantic_required=False,
        max_findings=100, scan_columns=spec['scan_columns'])
    value = result.data()
    for finding in value['findings']:
        finding.update(raw_score=0.60, score_meaning='uncalibrated_rule_score')
    return dict(parsed=asdict(parsed), result=value)


def run_worker(scan):
    request = dict(task_key=scan.lab.case.task.task_key, domain='data-lab:' + str(scan.lab.attempt.attempt_id),
        scan_id=str(scan.scan_id), asset_id=str(scan.asset_id), asset_version_id=str(scan.asset_version_id),
        actor_id=scan.lab.attempt.student_id, created_at=scan.created_at.isoformat())
    try:
        result = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).with_name('worker.py'))],
            input=json.dumps(request), text=True, capture_output=True, timeout=6,
            cwd=Path(__file__).resolve().parents[2], check=False)
    except (subprocess.TimeoutExpired, OSError):
        raise ScanFailure('PARSER_TIMEOUT_OR_UNAVAILABLE') from None
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise ScanFailure('PARSER_FAILED')
    try:
        value = json.loads(result.stdout)
        if 'error' in value:
            raise ScanFailure(value['error'])
        return value
    except (ValueError, KeyError, TypeError):
        raise ScanFailure('PARSER_FAILED') from None
