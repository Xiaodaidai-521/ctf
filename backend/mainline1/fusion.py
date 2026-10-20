"""Private rule/semantic fusion and explicitly configured same-row relation candidates."""
import copy
import json
from collections import Counter
from dataclasses import asdict, dataclass
from itertools import product
from uuid import UUID, uuid5

from .classification import canonical, require
from .parsing import InputError, fingerprint
from .rules import RuleResult
from .semantic import SemanticConfig, cell_key, run_semantic

FUSION_VERSION = 'conservative-fusion-v1'


@dataclass(frozen=True)
class CombinationSpec:
    rule_id: str
    version: str
    relation_type: str
    categories: tuple[str, ...]
    protection_level: str
    approval_ref: str | None = None
    test_only: bool = True


def overlap(a, b):
    if any(a[k] != b[k] for k in ('sheet_id', 'row', 'column', 'channel')):
        return False
    if a['span'] is None or b['span'] is None:
        return True
    return max(a['span']['start'], b['span']['start']) < min(a['span']['end'], b['span']['end'])


async def scan_context(parsed, rule_result, config=SemanticConfig(), *, backend=None, approval=None,
                       target_keys=None, context_parsed=None, combinations=(), cancelled=lambda: False):
    """Call from a managed worker, never create an unmanaged thread. Default live path disabled."""
    base = rule_result.data()
    policy = base['snapshot']['configuration']['policy']
    known = {c['category_id']: c for c in policy['categories']}
    require(len(combinations) <= 20 and len({r.rule_id for r in combinations}) == len(combinations), 'COMBINATION_CONFIG_INVALID')
    for rule in combinations:
        require(rule.rule_id and rule.version and rule.relation_type and 2 <= len(rule.categories) <= 4
                and len(set(rule.categories)) == len(rule.categories) and set(rule.categories) <= set(known)
                and rule.protection_level in policy['levels'], 'COMBINATION_CONFIG_INVALID')
        require((rule.test_only and base['snapshot']['meta']['environment'] == 'test')
                or not rule.test_only and bool(rule.approval_ref), 'COMBINATION_NOT_APPROVED')
    semantic = await run_semantic(parsed, rule_result, config, backend=backend, approval=approval,
                                  target_keys=target_keys, context_parsed=context_parsed, cancelled=cancelled)
    sid = base['profile']['scan_id']
    run_hash = fingerprint(dict(rule=base['request_fingerprint'], semantic=semantic['request_fingerprint'],
                                fusion=FUSION_VERSION, combinations=[asdict(r) for r in combinations]))
    prefix = f'private:semantic-run:{sid}:{run_hash}'
    cells = {cell_key(c): c for c in parsed.cells}
    sources = copy.deepcopy(base['findings'])
    sem_findings = []
    seen = set()
    for outcome in semantic['outcomes']:
        cell = cells[tuple(outcome['key'])]
        for item in outcome['findings']:
            try:
                start, end = cell.source_span(item['start'], item['end'])
                loc = dict(sheet_id=cell.sheet_id, row=cell.row, column=cell.column,
                           channel=cell.channel, kind='span', span=dict(start=start, end=end))
                reasons = {'MODEL_CANDIDATE_REQUIRES_REVIEW'}
            except InputError:
                loc = dict(sheet_id=cell.sheet_id, row=cell.row, column=cell.column,
                           channel=cell.channel, kind='cell', span=None)
                reasons = {'MODEL_CANDIDATE_REQUIRES_REVIEW', 'LOCATION_UNRELIABLE'}
            context = base['snapshot']['context']
            reasons.add('CONTEXT_CONFLICT' if context['confirmation'] == 'conflicted' else
                        'CONTEXT_UNCONFIRMED' if context['confirmation'] != 'confirmed' else 'CONTEXT_CONFIRMATION_NOT_MODEL_PROOF')
            if semantic['execution_mode'] == 'test_double':
                reasons.add('TEST_DOUBLE_NOT_REAL_SEMANTIC')
            key = canonical([item['category_id'], loc])
            if key in seen:
                continue
            seen.add(key)
            fid = str(uuid5(UUID(sid), run_hash + ':semantic:' + key))
            reasons.update(known[item['category_id']]['review_conditions'])
            sem_findings.append(dict(meta=base['profile']['meta'], finding_id=fid, scan_id=sid, kind='entity',
                locations=[loc], category_id=item['category_id'], judgment='conflict' if 'CONTEXT_CONFLICT' in reasons
                else 'insufficient' if 'LOCATION_UNRELIABLE' in reasons else 'pending_review',
                source_type='semantic', detector_id=config.provider + ':' + config.model,
                detector_version=config.revision or 'revision-unknown', source_finding_ids=[], relation_type=None,
                evidence=[dict(evidence_ref=prefix + ':evidence:' + outcome['request']['target']['id'] + ':' + e,
                               kind='model' if e.startswith('target:') else 'context', reason_code='VALIDATED_MODEL_EVIDENCE')
                          for e in item['evidence_ids']], uncertainty_reasons=sorted(reasons),
                raw_score=item['raw_score'], score_meaning='uncalibrated_model_score' if item['raw_score'] is not None else None,
                calibrated_probability=None, calibration_version=None, created_by=None, review_id=None))
    sources.extend(sem_findings)
    groups = {}
    for finding in sources:
        groups.setdefault(canonical([finding['category_id'], finding['locations']]), []).append(finding)
    effective = []

    def fused(parents, representative, reason):
        value = copy.deepcopy(representative)
        parent_ids = sorted({p['finding_id'] for p in parents})
        value.update(finding_id=str(uuid5(UUID(sid), run_hash + reason + canonical([parent_ids, value['category_id']]))),
                     source_type='fusion', source_finding_ids=parent_ids, detector_id=FUSION_VERSION,
                     detector_version=FUSION_VERSION, raw_score=None, score_meaning=None,
                     calibrated_probability=None, calibration_version=None)
        value['uncertainty_reasons'] = sorted({reason} | {r for p in parents for r in p['uncertainty_reasons']})
        value['evidence'] = list({canonical(e): e for p in parents for e in p['evidence']}.values())
        value['judgment'] = ('conflict' if any(p['judgment'] == 'conflict' for p in parents)
                             else 'insufficient' if any(p['judgment'] == 'insufficient' for p in parents)
                             else 'pending_review')
        if reason == 'CATEGORY_CONFLICT':
            value['judgment'] = 'conflict'
        return value

    for group in groups.values():
        if len(group) > 1:
            value = fused(group, group[0], 'RULE_SEMANTIC_AGREEMENT_NOT_CONFIRMATION')
            sources.append(value)
            effective.append(value)
        else:
            effective.append(group[0])
    conflicted = []
    for finding in effective:
        others = [f for f in effective if f['category_id'] != finding['category_id']
                  and any(overlap(a, b) for a in f['locations'] for b in finding['locations'])]
        if others:
            value = fused([finding] + others, finding, 'CATEGORY_CONFLICT')
            sources.append(value)
            conflicted.append(value)
        else:
            conflicted.append(finding)
    effective = conflicted
    relation_findings, relation_targets, relation_done = [], [], []
    rows = sorted({(c.sheet_id, c.row) for c in parsed.cells})
    for spec in combinations:
        for sheet, row in rows:
            if cancelled():
                raise InputError('TASK_CANCELLED')
            unit = dict(rule_id=spec.rule_id, sheet_id=sheet, row=row)
            relation_targets.append(unit)
            by_category = [[f for f in effective if f['category_id'] == category and any(
                loc['sheet_id'] == sheet and loc['row'] == row for loc in f['locations'])] for category in spec.categories]
            # Bound relation expansion before materializing cartesian products.
            count = 1
            for choices in by_category:
                count *= len(choices)
            require(count <= 100 and len(relation_findings) + count <= 1000, 'COMBINATION_RESOURCE_LIMIT')
            for members in product(*by_category):
                locations = [m['locations'][0] for m in members]
                if len({loc['column'] for loc in locations}) < len(locations):
                    continue  # Same-row *distinct-field* co-occurrence, not personal re-identification.
                parents = sorted({m['finding_id'] for m in members})
                relation_findings.append(dict(meta=base['profile']['meta'], finding_id=str(uuid5(UUID(sid), run_hash + spec.rule_id + canonical(parents))),
                    scan_id=sid, kind='combination', locations=locations, category_id=None, judgment='pending_review',
                    source_type='fusion', detector_id=spec.rule_id, detector_version=spec.version,
                    source_finding_ids=parents, relation_type=spec.relation_type,
                    evidence=list({canonical(e): e for m in members for e in m['evidence']}.values()),
                    uncertainty_reasons=['COOCCURRENCE_CANDIDATE_ONLY', 'NOT_REIDENTIFICATION_OR_LEGAL_CONCLUSION']
                    + (['PROPOSED_COMBINATION_TEST_ONLY'] if spec.test_only else []),
                    raw_score=None, score_meaning=None, calibrated_probability=None, calibration_version=None,
                    created_by=None, review_id=None))
            relation_done.append(unit)
    profile = copy.deepcopy(base['profile'])
    manifests = copy.deepcopy(base['manifests'])
    for finding in base['findings']:
        for evidence in finding['evidence']:
            if evidence['kind'] == 'rule':
                manifests[evidence['evidence_ref']] = rule_result.resolve_private(evidence['evidence_ref'])
    selected = {tuple(o['key']): o for o in semantic['outcomes']}
    done = [o['key'] for o in selected.values() if o['status'] == 'complete']
    failed = [o['key'] for o in selected.values() if o['status'] == 'failed']
    skipped = [list(key) for key in cells if key not in selected or selected[key]['status'] == 'not_run']

    def coverage(name, targets, done, skipped, failed, status, reasons, unit='cell'):
        for suffix, values in [('target', targets), ('processed', done), ('skipped', skipped), ('failed', failed)]:
            manifests[prefix + ':' + name + ':' + suffix] = values
        return dict(status=status, unit=unit, target_count=len(targets), processed_count=len(done),
                    skipped_count=len(skipped), failed_count=len(failed), ratio=len(done)/len(targets) if targets else None,
                    target_scope_ref=prefix + ':' + name + ':target',
                    processed_scope_ref=prefix + ':' + name + ':processed' if done else None,
                    skipped_scope_ref=prefix + ':' + name + ':skipped' if skipped else None,
                    failed_scope_ref=prefix + ':' + name + ':failed' if failed else None, reason_codes=reasons)
    status = 'not_run' if semantic['blocked_reason'] or not semantic['calls'] else 'failed' if failed and not done else 'partial' if failed or skipped else 'complete'
    reasons = sorted({o['error_code'] for o in semantic['outcomes'] if o['error_code']}
                     | ({'PARTIAL_TARGET_SELECTION'} if len(selected) < len(cells) else set())
                     | ({'TEST_DOUBLE_NOT_REAL_SEMANTIC'} if semantic['execution_mode'] == 'test_double' else set()))
    profile['coverage']['semantic'] = coverage('semantic', [list(k) for k in cells], done, skipped, failed, status, reasons)
    if combinations:
        profile['coverage']['combination'] = coverage('combination', relation_targets, relation_done, [], [],
            'complete', ['CONFIGURED_ROW_RELATIONS_ONLY'] + (['PROPOSED_COMBINATION_TEST_ONLY'] if any(s.test_only for s in combinations) else []), 'relation')
    categories = Counter(f['category_id'] for f in effective if f['category_id'] is not None)
    levels = [known[c]['protection_level'] for c in categories]
    levels.extend(spec.protection_level for spec in combinations if any(f['detector_id'] == spec.rule_id for f in relation_findings))
    profile.update(profile_id=str(uuid5(UUID(sid), 'profile:' + run_hash)), finding_ids=[f['finding_id'] for f in effective + relation_findings],
        combination_finding_ids=[f['finding_id'] for f in relation_findings],
        category_counts=[dict(category_id=c, count=categories[c]) for c in sorted(categories)],
        protection_level=max(levels, key=policy['levels'].index) if levels else None,
        review_status='pending' if effective or failed or relation_findings else 'not_required',
        detector_versions=sorted(set(profile['detector_versions'] + [FUSION_VERSION, config.provider + ':' + config.model, config.revision or 'revision-unknown'])))
    limits = set(profile['limitations']) - {'SEMANTIC_NOT_RUN'}
    if combinations:
        limits.discard('COMBINATION_NOT_RUN')
    if status != 'complete':
        limits.add('SEMANTIC_' + status.upper())
    if semantic['execution_mode'] == 'test_double':
        limits.add('TEST_DOUBLE_NOT_REAL_SEMANTIC')
    if config.revision is None:
        limits.add('MODEL_REVISION_UNPINNED')
    if any(spec.test_only for spec in combinations):
        limits.add('PROPOSED_COMBINATION_TEST_ONLY')
    profile['limitations'] = sorted(limits)
    profile['quality'] = 'complete' if (status == 'complete' and profile['coverage']['rule']['status'] == 'complete'
        and semantic['execution_mode'] == 'live' and not any(s.test_only for s in combinations)) else 'partial'
    for outcome in semantic['outcomes']:
        request = outcome['request']
        for evidence_id in [request['target']['id']] + [a['id'] for a in request['auxiliary']]:
            manifests[prefix + ':evidence:' + request['target']['id'] + ':' + evidence_id] = dict(
                target_id=request['target']['id'], evidence_id=evidence_id, request_fingerprint=fingerprint(request))
    snapshot = dict(base['snapshot'], semantic=semantic['snapshot'], fusion_version=FUSION_VERSION,
                    combination_config=[asdict(r) for r in combinations], rule_request_fingerprint=base['request_fingerprint'])
    return RuleResult(json.dumps(dict(snapshot=snapshot, request_fingerprint=run_hash, findings=effective + relation_findings,
        source_findings=sources, profile=profile, manifests=manifests, rule_cell_outcomes=base['cell_outcomes'],
        semantic_execution=semantic), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False))
