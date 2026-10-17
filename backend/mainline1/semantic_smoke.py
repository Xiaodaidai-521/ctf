"""A/B/C preflight only: no model loading, network call or effectiveness estimate."""
from dataclasses import replace

from .classification import require
from .parsing import fingerprint
from .semantic import prepare_requests


def abc_preflight(parsed, rule_result, config, *, target_keys, context_parsed=None):
    groups = {mode: prepare_requests(parsed, rule_result, replace(config, mode=mode),
                                     target_keys=target_keys, context_parsed=context_parsed) for mode in ('B', 'C')}
    b = [(list(key), request.data()['target']) for key, request in groups['B']]
    c = [(list(key), request.data()['target']) for key, request in groups['C']]
    require(b == c, 'EXPERIMENT_TARGET_MISMATCH')
    selected = {tuple(key) for key, _ in b}
    baseline = [f['finding_id'] for f in rule_result.data()['findings'] if any(
        (loc['sheet_id'], loc['row'], loc['column'], loc['channel']) in selected for loc in f['locations'])]
    return dict(template_version='context-semantic-v1', targets_hash=fingerprint(b), target_count=len(b),
                A={'execution': 'rule_only', 'rule_fingerprint': rule_result.data()['request_fingerprint'],
                   'evaluated_targets': [key for key, _ in b], 'finding_ids': baseline},
                B={'execution': 'not_run', 'input_hash': fingerprint([r.data() for _, r in groups['B']])},
                C={'execution': 'not_run', 'input_hash': fingerprint([r.data() for _, r in groups['C']]),
                   'input_limits': sorted({reason for _, r in groups['C'] for reason in r.data()['limitations']})},
                target_equivalence='Passed', semantic_effectiveness='Blocked', metrics=None)
