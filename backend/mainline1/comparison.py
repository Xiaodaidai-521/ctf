"""Conservative fixed-profile comparison. No public content fingerprints."""
from collections import defaultdict
from copy import deepcopy
from uuid import UUID, uuid5

from .classification import RuleConfiguration, require
from .parsing import fingerprint
from .review import binding, partition


def compare_bundles(before, after):
    a, b = before['profile'], after['profile']
    require(partition(a) == partition(b) and a['asset']['asset_id'] == b['asset']['asset_id'], 'COMPARISON_SCOPE_MISMATCH')
    # Coordinates are comparable only on the exact same private input and parse mapping.
    keys = ('asset', 'scope_hash', 'parser_version', 'parser_config_hash', 'parsed_cells_hash', 'parse_metadata_hash')
    same = all(before['snapshot'].get(k) == after['snapshot'].get(k) for k in keys)
    result = dict(meta=deepcopy(b['meta']), comparison_id=str(uuid5(UUID(a['profile_id']), b['profile_id'])),
        before_scan_id=a['scan_id'], after_scan_id=b['scan_id'], before_profile_id=a['profile_id'],
        after_profile_id=b['profile_id'], before_asset_version_id=a['asset']['asset_version_id'],
        after_asset_version_id=b['asset']['asset_version_id'], matching_version='exact-private-input-v1',
        added=[], disappeared=[], category_changes=[], unmatched=[], limitations=[])
    if not same:
        result.update(unmatched=sorted(set(a['finding_ids'] + b['finding_ids'])),
                      limitations=['INPUT_CHANGED_NO_STABLE_ENTITY_LINEAGE'])
        return result
    left, right = defaultdict(list), defaultdict(list)
    for bundle, groups in ((before, left), (after, right)):
        for finding in bundle['findings']:
            # Multiple findings on a location are ambiguous, not greedily paired.
            key = fingerprint([finding['kind'], finding['locations'], finding.get('relation_type')])
            groups[key].append(finding)
    consumed_left, consumed_right = set(), set()
    for key in sorted(set(left) & set(right)):
        old, new = left[key], right[key]
        if len(old) > 1 or len(new) > 1:
            result['unmatched'].extend(f['finding_id'] for f in old)
            result['unmatched'].extend(f['finding_id'] for f in new)
            consumed_left.add(key)
            consumed_right.add(key)
        elif old[0]['category_id'] != new[0]['category_id']:
            result['category_changes'].append(dict(before_finding_id=old[0]['finding_id'],
                after_finding_id=new[0]['finding_id']))
            consumed_left.add(key)
            consumed_right.add(key)
        else:
            consumed_left.add(key)
            consumed_right.add(key)
    remaining_left = [f for key, group in left.items() if key not in consumed_left for f in group]
    remaining_right = [f for key, group in right.items() if key not in consumed_right for f in group]
    # A one-to-one same-kind/category pair at changed coordinates may be a move.
    # Without stable entity lineage, report both as unmatched rather than inventing
    # an addition/disappearance or matching by a coordinate alone.
    possible = []
    for old in remaining_left:
        candidates = [new for new in remaining_right if new['kind'] == old['kind']]
        if len(candidates) == 1:
            reverse = [prior for prior in remaining_left if prior['kind'] == candidates[0]['kind']]
            if len(reverse) == 1:
                possible.extend([old['finding_id'], candidates[0]['finding_id']])
    possible = set(possible)
    result['unmatched'].extend(sorted(possible))
    result['added'].extend(f['finding_id'] for f in remaining_right if f['finding_id'] not in possible)
    result['disappeared'].extend(f['finding_id'] for f in remaining_left if f['finding_id'] not in possible)
    if result['unmatched']:
        result['limitations'].append('AMBIGUOUS_LOCATION')
    if a['quality'] != 'complete' or b['quality'] != 'complete':
        result['limitations'].append('INCOMPLETE_DETECTION_NOT_PROOF_OF_ABSENCE')
        result['unmatched'].extend(result['disappeared'])
        result['unmatched'].extend(result['added'])
        result['added'], result['disappeared'] = [], []
    return result


def exact_review_reuse(before, after):
    return (binding(before) == binding(after)
            and before.get('regrade') == after.get('regrade')
            and before['snapshot'].get('engine_version') == after['snapshot'].get('engine_version'))


def regrade_configuration(bundle, configuration):
    """Only a change to level mapping/version can reuse the fixed evidence."""
    new = RuleConfiguration.load(configuration).data()
    old = deepcopy(bundle.get('regrade', {}).get('configuration', bundle['snapshot']['configuration']))
    require(new['policy']['version'] != old['policy']['version'], 'POLICY_VERSION_REQUIRED')
    require(not bundle['profile']['combination_finding_ids'], 'RESCAN_REQUIRED')
    def evidence_projection(config):
        value = deepcopy(config)
        for key in ('version', 'content_hash', 'meta', 'levels'):
            value['policy'].pop(key)
        for category in value['policy']['categories']:
            category.pop('protection_level')
        return value
    require(evidence_projection(old) == evidence_projection(new), 'RESCAN_REQUIRED')
    categories = {c['category_id']: c for c in new['policy']['categories']}
    require(all(f['category_id'] in categories for f in bundle['findings']), 'RESCAN_REQUIRED')
    return new
