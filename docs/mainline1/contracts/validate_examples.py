"""Design-only checks. No application imports, database, filesystem mutation or network."""
import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

HERE = Path(__file__).resolve().parent


def expand(base, patches):
    result = copy.deepcopy(base)
    for patch in patches:
        parts = [p.replace('~1', '/').replace('~0', '~') for p in patch['path'].split('/')[1:]]
        target = result
        for part in parts[:-1]:
            target = target[part]
        key = parts[-1]
        if patch['op'] == 'remove':
            del target[key]
        elif patch['op'] in ('add', 'replace'):
            if patch['op'] == 'replace':
                assert key in target
            target[key] = copy.deepcopy(patch['value'])
        else:
            raise ValueError('Unsupported fixture patch')
    return result


def invariant_errors(objects):
    """Finite draft invariants only; this is NOT the future business validator."""
    errors = set()
    asset = objects.get('AssetVersionRef')
    snap = objects.get('ScanRunSnapshot')
    profile = objects.get('SensitivityProfile')
    plan = objects.get('RedactionPlan')
    state = objects.get('ProfileApplicability')
    finding = objects.get('Finding')
    result = objects.get('ScanResult')
    context = objects.get('BusinessContext')
    review = objects.get('ReviewRecord')
    metas = [o['meta'] for o in objects.values()]
    for meta in metas:
        if any(meta[k] != metas[0][k] for k in ('domain_id', 'environment', 'evaluation_run_id')):
            errors.add('DOMAIN_MISMATCH')
    if asset:
        if any(o.get('asset', asset['asset']) != asset['asset'] for o in objects.values()):
            errors.add('ASSET_VERSION_MISMATCH')
        if asset['state'] == 'deleted' and plan:
            errors.add('ASSET_DELETED')
    for o in objects.values():
        for layer in o.get('coverage', {}).values():
            target = layer['target_count']
            ratio = layer['ratio']
            processed = layer['processed_count']
            if target in (None, 0):
                if ratio is not None:
                    errors.add('COVERAGE_INVALID')
            elif ratio is None or abs(ratio - processed / target) > 1e-9:
                errors.add('COVERAGE_INVALID')
            if target is not None and processed + layer['skipped_count'] + layer['failed_count'] > target:
                errors.add('COVERAGE_INVALID')
            if layer['status'] == 'complete' and (target is None or processed != target or layer['failed_count'] or layer['skipped_count']):
                errors.add('COVERAGE_INVALID')
            if layer['status'] in ('not_run', 'excluded') and processed:
                errors.add('COVERAGE_INVALID')
    if snap:
        required = ['parse', 'rule']
        required += ['semantic'] if snap['semantic_required'] else []
        required += ['combination'] if snap['combination_required'] else []
        for o in (profile, result):
            if o and o['quality'] == 'complete' and any(o['coverage'][key]['status'] != 'complete' for key in required):
                errors.add('QUALITY_INCOMPLETE')
    if result:
        total, processed, ratio = result['total_count'], result['processed_count'], result['progress_ratio']
        if total in (None, 0):
            if ratio is not None:
                errors.add('PROGRESS_INVALID')
        elif processed > total or ratio is None or abs(ratio - processed / total) > 1e-9:
            errors.add('PROGRESS_INVALID')
        if result['task_status'] in ('failed', 'cancelled') and result['quality'] == 'complete':
            errors.add('QUALITY_INCOMPLETE')
        if objects.get('TaskReference', {}).get('status', result['task_status']) != result['task_status']:
            errors.add('TASK_STATE_MISMATCH')
    if context and context['confirmation'] == 'confirmed':
        if context['source'] == 'model_inferred' or context['confirmed_by'] is None or context['confirmed_at'] is None:
            errors.add('CONTEXT_INVALID')
    if finding:
        if finding['source_type'] == 'manual' and (finding['detector_id'] is not None or finding['detector_version'] is not None or finding['created_by'] is None or finding['review_id'] is None):
            errors.add('MANUAL_PROVENANCE_INVALID')
        if finding['source_type'] != 'manual' and (finding['detector_id'] is None or finding['detector_version'] is None):
            errors.add('DETECTOR_PROVENANCE_INVALID')
        if finding['calibrated_probability'] is not None and finding['calibration_version'] is None:
            errors.add('CALIBRATION_INVALID')
        if finding['source_type'] == 'fusion' and len(set(finding['source_finding_ids'])) < 2:
            errors.add('FUSION_PROVENANCE_INVALID')
        mappings = objects.get('ParsedAsset', {}).get('mappings', [])
        for loc in finding['locations']:
            span = loc['span']
            if (loc['kind'] == 'span') != (span is not None):
                errors.add('LOCATION_MISMATCH')
            if span:
                lengths = [m['source_length'] for m in mappings if all(m['location'][k] == loc[k] for k in ('sheet_id', 'row', 'column', 'channel'))]
                if span['start'] >= span['end'] or (lengths and span['end'] > lengths[0]):
                    errors.add('LOCATION_MISMATCH')
    if review:
        expected = {'confirm': 'confirmed', 'correct': 'corrected', 'false_positive': 'false_positive', 'add_manual': 'manual_added'}
        if review['request_status'] == 'rejected' or review['workflow_status'] == 'pending':
            if review['conclusion'] is not None or review['successor_profile_id'] is not None:
                errors.add('REVIEW_CONCLUSION_INVALID')
        elif review['conclusion'] != expected[review['action']] or review['successor_profile_id'] is None:
            errors.add('REVIEW_CONCLUSION_INVALID')
    if plan:
        if len(plan['operations']) != plan['operation_count']:
            errors.add('PLAN_COUNT_INVALID')
        if plan['status'] == 'ready' and (plan['unresolved'] or plan['validation_errors']):
            errors.add('PLAN_NOT_READY')
        if state and state['status'] != 'current':
            errors.add({'superseded': 'PROFILE_SUPERSEDED', 'reevaluation_required': 'PROFILE_REEVALUATION_REQUIRED', 'unverifiable_deleted': 'PROFILE_UNVERIFIABLE'}[state['status']])
        if state and state['status'] != 'current' and state['usable_for_new_decision']:
            errors.add('APPLICABILITY_INVALID')
        for index, left in enumerate(plan['operations']):
            for right in plan['operations'][index + 1:]:
                a, b = left['target'], right['target']
                same_column = all(a[k] == b[k] for k in ('sheet_id', 'column'))
                if not same_column:
                    continue
                if 'drop_column' in (left['type'], right['type']):
                    errors.add('PLAN_CONFLICT')
                elif a['row'] == b['row'] and a['channel'] == b['channel']:
                    if 'mask_cell' in (left['type'], right['type']):
                        errors.add('PLAN_CONFLICT')
                    elif a['span'] and b['span'] and max(a['span']['start'], b['span']['start']) < min(a['span']['end'], b['span']['end']):
                        errors.add('PLAN_CONFLICT')
    return sorted(errors)


def main():
    schema = json.loads((HERE / 'schema.json').read_text(encoding='utf-8'))
    examples = json.loads((HERE / 'examples.json').read_text(encoding='utf-8'))
    catalog = json.loads((HERE / 'catalog.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    assert len(catalog) == 14 and all(c['approval_status'] == 'proposed' for c in catalog)
    checked, rejected, business_refusals = 0, 0, 0
    seen = set()
    for case in examples['cases']:
        objects = expand(examples['base_objects'], case['patches'])
        failures = []
        for name, value in objects.items():
            seen.add(name)
            assert name in schema['$defs'], name
            validator = Draft202012Validator(dict(schema, **{'$ref': '#/$defs/' + name}), format_checker=FormatChecker())
            failures.extend(validator.iter_errors(value))
            checked += 1
        valid = not failures
        assert valid == case['expected_schema_valid'], (case['name'], [e.message for e in failures][:3])
        if valid:
            actual = invariant_errors(objects)
            assert actual == sorted(case['expected_invariant_errors']), (case['name'], actual, case['expected_invariant_errors'])
            business_refusals += bool(actual)
        else:
            rejected += 1
        print('PASS ' + case['name'])
    assert {c['name'] for c in catalog} <= seen
    print(f'PASS schema/catalog; {len(examples["cases"])} scenarios; {checked} object checks; {rejected} schema-negative cases; {business_refusals} invariant-refusal cases')
    print('DESIGN ONLY: no application behavior, database concurrency, permission enforcement or real model was tested.')


if __name__ == '__main__':
    main()
