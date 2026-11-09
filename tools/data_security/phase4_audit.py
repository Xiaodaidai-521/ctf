"""Bounded phase-four metadata observation; never grants acceptance or authorization."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from tools.data_security import dependencies, watchdog
from tools.data_security.isolation import ROOT
from tools.data_security.verify_phase1 import SECRET_PATTERNS, git

BASELINE = '4619af208156420d6a01a1937846d5a4473c3665'
RECORDS = Path('/home/hatch/workspace/data-security-seven-phases')
EVIDENCE = RECORDS / 'evidence/phase-04'
MAPPING = RECORDS / 'sessions/phase-04.json'
MAIN = Path('/home/hatch/workspace/ctf-repo')
# E4/preflight-records.json and the report pin this original, read-only worktree.
MAIN_PIN = {'head': 'be67a4e59d4a28ab07f3a55b295081c5831acaaa',
            'branch': 'fix/event-id-over-64', 'dirty': False}
TEST_DELTAS = {
    'backend/data_security/tests/test_phase2_boundaries.py': (
        ('scan(ROOT, phase=3)', 'scan(ROOT, phase=4)'),),
    'backend/data_security/tests/test_phase3_dependencies.py': (
        ('test_actual_phase3_tree_', 'test_actual_current_tree_'),
        ('scan(ROOT, phase=3)', 'scan(ROOT, phase=4)'),
        ("({'phase': 4, 'version': 'phase-boundary.v1'},", "({'phase': 5, 'version': 'phase-boundary.v1'},")),
    'backend/ai_assistant/test_phase3_content.py': (
        ('        self.task = SimpleNamespace(id=1,',
         '        from legal.models import LegalAnalysisTask\n        self.task = LegalAnalysisTask(id=1,'),),
    'backend/audit/test_phase3_bootstrap.py': (
        ('        task = SimpleNamespace(id=1,',
         '        from legal.models import LegalAnalysisTask\n        task = LegalAnalysisTask(id=1,'),),
}


def main():
    if Path.cwd() != ROOT or ROOT != Path('/home/hatch/workspace/ctf-data-security'):
        raise RuntimeError('ISOLATED_WORKTREE_REQUIRED')
    sys.path.insert(0, str(ROOT / 'backend'))
    from data_security.tests.synthetic import samples
    from data_security.tests.phase2_fixtures import root_key, KeyPurpose

    started = datetime.now(timezone.utc).isoformat()
    issues, hygiene = [], []
    head, branch = git('rev-parse', 'HEAD'), git('branch', '--show-current')
    original = set(git('ls-tree', '-r', '--name-only', BASELINE).splitlines())
    changed = set(git('diff', '--name-only', BASELINE).splitlines())
    untracked = set(git('ls-files', '--others', '--exclude-standard').splitlines())
    changed |= untracked
    patch = subprocess.check_output(['git', 'diff', '--no-ext-diff', '--binary', BASELINE], cwd=ROOT)
    ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', BASELINE, head],
                              cwd=ROOT, capture_output=True).returncode == 0
    frozen = {p for p in original | changed if p.startswith('backend/data_security/contracts/') or
              p.endswith('.py') and dependencies.owner(dependencies.module_name(p)) in {'M0', 'M1', 'M2', 'M3'}}
    frozen_changes = sorted(changed & frozen)
    old_tests = sorted(p for p in changed & original if 'tests' in Path(p).parts or
        Path(p).name == 'tests.py' or Path(p).name.startswith('test_') or
        '.test.' in Path(p).name or '.spec.' in Path(p).name)
    main_state = {'head': git('rev-parse', 'HEAD', root=MAIN),
                  'branch': git('branch', '--show-current', root=MAIN),
                  'dirty': bool(git('status', '--porcelain', '--untracked-files=all', root=MAIN))}
    if main_state != MAIN_PIN:
        issues.append('ORIGINAL_WORKTREE_CHANGED')
    if not ancestor or branch != 'feat/data-security' or frozen_changes:
        issues.append('WORKTREE_OR_FROZEN_SCOPE')
    checked, findings = dependencies.scan(ROOT, phase=4)
    if findings:
        issues.append('DEPENDENCIES')
    declaration = ROOT / 'tools/data_security/phase-boundary.json'
    if declaration.is_symlink() or json.loads(declaration.read_bytes()) != {'phase': 4, 'version': 'phase-boundary.v1'}:
        issues.append('PHASE_DECLARATION')

    payloads = [sample.text.encode() for sample in samples()]
    for label in ('data', 'other', *(purpose.value for purpose in KeyPurpose)):
        payloads.extend((root_key(label), root_key(label).hex().encode()))
    patterns = {**SECRET_PATTERNS,
        'phase3-generated-credential': re.compile(rb'\bsynthetic-[0-9a-f]{64}\b'),
        'age-secret-identity': re.compile(rb'\bAGE-SECRET-KEY-1[0-9A-Z]{50,}\b'),
        'bearer-credential-shaped': re.compile(rb'\bBearer[ \t]+[A-Za-z0-9_.~+/-]{32,}={0,2}'),
    }
    source, artifacts, hashes, records, bindings, snapshots, historical_tests = {}, [], {}, [], [], [], []
    paths = {ROOT / p for p in changed}
    paths |= {RECORDS / '实施报告.md', RECORDS / 'PHASE4-BRIEF.md', MAPPING}
    if MAPPING.with_suffix('.control.json').exists():
        paths.add(MAPPING.with_suffix('.control.json'))
    paths.update(p for p in (RECORDS / 'logs').glob('*phase-04*') if p.is_file())
    paths.update((ROOT / '.state/pg-run').glob('*.log'))
    if not EVIDENCE.is_dir() or EVIDENCE.is_symlink():
        issues.append('EVIDENCE_DIRECTORY_INVALID')
    else:
        for p in (EVIDENCE, *EVIDENCE.rglob('*')):
            if p.is_symlink():
                hygiene.append({'file': str(p), 'code': 'EVIDENCE_SYMLINK'})
            elif p.is_dir():
                if p.stat().st_mode & 0o077:
                    hygiene.append({'file': str(p), 'code': 'EVIDENCE_DIRECTORY_PERMISSIONS'})
            else:
                paths.add(p)
    for p in sorted(paths):
        relative = p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else None
        if p.is_symlink():
            hygiene.append({'file': str(p), 'code': 'SYMLINK'})
            continue
        if not p.is_file():
            if relative in changed:
                source[relative] = {'deleted': True, 'sha256': None}
            else:
                hygiene.append({'file': str(p), 'code': 'MISSING_OBSERVED_FILE'})
            continue
        data = p.read_bytes()
        digest = hashes[p] = hashlib.sha256(data).hexdigest()
        metadata = {'file': str(p), 'sha256': digest, 'bytes': len(data), 'mode': oct(p.stat().st_mode & 0o777)}
        if any(value in data for value in payloads):
            hygiene.append({'file': str(p), 'code': 'KNOWN_SYNTHETIC_VALUE'})
        for name, pattern in patterns.items():
            if pattern.search(data):
                hygiene.append({'file': str(p), 'code': name})
        if relative in changed:
            prior = subprocess.check_output(['git', 'show', BASELINE + ':' + relative], cwd=ROOT) if relative in original else None
            source[relative] = {**metadata, 'baseline_sha256': hashlib.sha256(prior).hexdigest() if prior is not None else None,
                                'untracked': relative in untracked, 'deleted': False,
                                'module_owner': dependencies.owner(dependencies.module_name(relative)) if p.suffix == '.py' else None}
            if relative in old_tests:
                expected, exact = prior, relative in TEST_DELTAS
                for before, after in TEST_DELTAS.get(relative, ()):
                    exact = exact and expected.count(before.encode()) == 1
                    expected = expected.replace(before.encode(), after.encode(), 1)
                exact = exact and expected == data
                approved = relative in tuple(TEST_DELTAS)[:2]
                historical_tests.append({'file': relative, 'phase_declaration_update_authorized': approved,
                    'owner_fixture_update_not_separately_user_approved': relative in tuple(TEST_DELTAS)[2:],
                    'exact_described_delta': exact, 'assertions_unchanged_by_fixture_delta': exact if not approved else None})
                if not approved or not exact:
                    issues.append('HISTORICAL_TEST_CHANGE_NOT_APPROVED' if not approved else 'HISTORICAL_TEST_DELTA_MISMATCH')
            continue
        is_evidence = p.is_relative_to(EVIDENCE)
        artifacts.append({**metadata, 'observation': 'snapshot-not-current-acceptance',
                          'unsealed_log': p.suffix == '.log' and not p.with_suffix('.json').is_file()})
        if not is_evidence:
            continue
        if p.stat().st_mode & 0o077:
            hygiene.append({'file': str(p), 'code': 'EVIDENCE_PERMISSIONS'})
        if p.suffix != '.json':
            continue
        try:
            record = json.loads(data)
        except ValueError:
            hygiene.append({'file': str(p), 'code': 'INVALID_EVIDENCE_JSON'})
            continue
        stack, codes = [record], []
        while stack:
            item = stack.pop()
            if type(item) is dict:
                for key, value in item.items():
                    if key == 'returncode' or key.endswith('exit_code'):
                        if type(value) is int:
                            codes.append(value)
                        else:
                            hygiene.append({'file': str(p), 'code': 'INVALID_EXIT_CODE'})
                    if type(value) in (dict, list):
                        stack.append(value)
            elif type(item) is list:
                stack.extend(item)
        if codes:
            records.append({'file': str(p), 'exit_codes': codes, 'has_nonzero': any(code != 0 for code in codes)})
        if type(record) is not dict:
            continue
        output = record.get('output', record.get('log', p.with_suffix('.log').name if 'log_sha256' in record else None))
        if output is not None:
            target = Path(output) if type(output) is str else Path('/')
            target = target if target.is_absolute() else EVIDENCE / target
            if not target.is_relative_to(EVIDENCE) or '..' in target.parts or target.is_symlink():
                hygiene.append({'file': str(p), 'code': 'INVALID_OUTPUT_REFERENCE'})
            else:
                bindings.append((p, target, record.get('output_sha256', record.get('log_sha256'))))
        for item in record.get('source_snapshots', []) + record.get('artifacts', []):
            snapshots.append((p, Path(item['path']), item.get('sha256')))
        for name, sha in record.get('source_sha256', {}).items():
            snapshots.append((p, ROOT / name, sha))
    links = []
    for record, target, expected in bindings:
        actual = hashes.get(target)
        match = actual is not None and actual == expected
        links.append({'file': str(record), 'output': str(target), 'observed_sha256': actual,
                      'recorded_hash_present': expected is not None, 'recorded_hash_matches': match})
        if not match:
            hygiene.append({'file': str(record), 'code': 'EVIDENCE_OUTPUT_HASH_UNBOUND_OR_MISMATCH'})
    if hygiene:
        issues.append('HYGIENE_OR_EVIDENCE_INTEGRITY')
    if set(old_tests) - {item['file'] for item in historical_tests}:
        issues.append('HISTORICAL_TEST_DELETED_OR_UNREADABLE')

    supervision = {'mapping': str(MAPPING), 'watchdog_live': False, 'single_executor': False}
    try:
        config = watchdog.load(MAPPING)
        watchdog.validate(config)
        if config['phase'] != 4 or config.get('baseline_candidate') != BASELINE or config.get('branch') != branch:
            raise ValueError('WRONG_PHASE_MAPPING')
        watcher = watchdog.process(config.get('watchdog_pid'))
        executions = watchdog.session_processes(config)
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(config['checked_at'])).total_seconds()
        argv = watcher['argv'] if watcher else []
        mapped = (argv.count('--mapping') == 1 and argv.index('--mapping') + 1 < len(argv) and
                  argv[argv.index('--mapping') + 1] == str(MAPPING) and
                  (str(ROOT / 'tools/data_security/watchdog.py') in argv or 'tools.data_security.watchdog' in argv))
        live = bool(watcher and mapped and watcher['cwd'] == str(ROOT) and
                    watcher['start_ticks'] == config.get('watchdog_start_ticks') and 0 <= age < 120)
        observations = {key: watchdog.observation(config[key], config.get('last_observation', {}).get(key))
                        for key in ('run_log', 'session_record')}
        complete, accepted = watchdog.report_state((RECORDS / '实施报告.md').read_text(), 4, config.get('candidate_sha'))
        supervision.update(session_id=config['session_id'], watchdog_pid=watcher['pid'] if watcher else None,
            watchdog_live=live, watchdog_phase_mapping_matches=mapped, heartbeat_age_seconds=round(age, 3),
            single_executor=len(executions) == 1, executor_pids=[item['pid'] for item in executions],
            operator_state=config.get('operator_state'), observations=observations,
            candidate_recorded=bool(config.get('candidate_sha')), execution_complete_recorded=complete,
            independent_acceptance_recorded=accepted, restart_exercised_by_this_audit=False)
        if not (live and len(executions) == 1 and watcher['pid'] != executions[0]['pid'] and
                config.get('operator_state') == 'active' and
                all(v['exists'] and not v['blocked'] and not v['pending'] for v in observations.values())):
            issues.append('SUPERVISION_NOT_CONFIRMED')
    except (OSError, ValueError, KeyError, TypeError):
        issues.append('INVALID_OR_MISSING_SUPERVISION')

    print(json.dumps({'phase': 4, 'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(),
        'scope': {'baseline': BASELINE, 'head': head, 'branch': branch, 'baseline_ancestor': ancestor,
            'tracked_diff_sha256': hashlib.sha256(patch).hexdigest(), 'changed_paths': sorted(changed),
            'untracked_paths': sorted(untracked), 'source_manifest': source,
            'frozen_m0_m3_files': len(frozen), 'frozen_m0_m3_changes': frozen_changes,
            'old_test_changes': historical_tests, 'original_worktree': main_state,
            'original_worktree_matches_preflight_pin': main_state == MAIN_PIN,
            'limitation': 'exact observed diff inventory, not blanket authorization of every product change'},
        'dependencies': {'phase': 4, 'checked_python_files': checked, 'violations': [
            {'file': v.file, 'line': v.line, 'code': v.code} for v in findings]},
        'artifact_manifest': artifacts, 'evidence_output_bindings': links,
        'historical_snapshot_references': [{'file': str(p), 'target': str(target),
            'target_in_bounded_scan': target in hashes, 'matches_observed_snapshot': hashes[target] == sha if target in hashes else None,
            'current_immutable_result': False} for p, target, sha in snapshots],
        'recorded_command_results': records, 'historical_nonzero_records': sum(r['has_nonzero'] for r in records),
        'history_policy': 'all nonzero records retained; no later run silently supersedes them; unsealed/live logs and early closeout/preflight references are snapshots',
        'hygiene': {'files_checked': len(hashes), 'violations': hygiene,
            'limitation': 'known synthetic values, deterministic fixture keys and credential shapes only; no universal detector, private key store or full SDK transcript scan'},
        'supervision': supervision, 'issues': sorted(set(issues)),
        'gate_status': 'metadata observation only; not phase completion, independent acceptance, or next-phase authorization'},
        ensure_ascii=False, indent=2))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
