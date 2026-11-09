"""Phase-five scope, evidence and supervision observation; never signs acceptance."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

from tools.data_security import dependencies, watchdog
from tools.data_security.isolation import ROOT
from tools.data_security.verify_phase1 import SECRET_PATTERNS

BASELINE = '3c8fc8e3ed49d60582c0b46bdb2d4792d4244e0a'
RECORDS = Path('/home/hatch/workspace/data-security-seven-phases')
EVIDENCE = RECORDS / 'evidence/phase-05'
MAIN = Path('/home/hatch/workspace/ctf-repo')


def git(*args, root=ROOT):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def main():
    if Path.cwd() != ROOT:
        raise RuntimeError('ISOLATED_WORKTREE_REQUIRED')
    issues = []
    head = git('rev-parse', 'HEAD')
    ancestors = {sha: subprocess.run(['git', 'merge-base', '--is-ancestor', sha, head],
        cwd=ROOT, capture_output=True).returncode == 0 for sha in (
        BASELINE, '34ce6059389a519626eebe9747e80a2b03488c43',
        '4619af208156420d6a01a1937846d5a4473c3665', '65ef487fab356dfd0eddaa4e3cef29bf85d44558',
        '2970a4cb18103b8de4ac7f04a4ea1aa6322b5989')}
    branch = git('branch', '--show-current')
    if branch != 'feat/data-security' or not all(ancestors.values()):
        issues.append('BASELINE_OR_BRANCH')
    main_state = {'head': git('rev-parse', 'HEAD', root=MAIN),
                  'branch': git('branch', '--show-current', root=MAIN),
                  'dirty': bool(git('status', '--porcelain', root=MAIN))}
    if main_state != {'head': 'be67a4e59d4a28ab07f3a55b295081c5831acaaa',
                       'branch': 'fix/event-id-over-64', 'dirty': False}:
        issues.append('MAIN_WORKTREE_CHANGED')
    changed = set(git('diff', '--name-only', BASELINE).splitlines())
    changed.update(git('ls-files', '--others', '--exclude-standard').splitlines())
    frozen = [p for p in changed if p.startswith('backend/data_security/contracts/') or
              p in ('backend/ctf_backend/security_bootstrap.py', 'backend/mainline1/planning.py',
                    'backend/mainline1/config/rule-baseline-v1.json')]
    if frozen:
        issues.append('FROZEN_CONTRACT_OR_APPROVAL_CHANGED')
    count, findings = dependencies.scan(ROOT, phase=5)
    if findings:
        issues.append('DEPENDENCY_VIOLATIONS')
    test_changes = []
    for name in sorted(changed):
        if not name.endswith('.py') or not ('/tests/' in name or Path(name).name.startswith('test_')):
            continue
        prior = subprocess.run(['git', 'show', BASELINE + ':' + name], cwd=ROOT, capture_output=True)
        if prior.returncode:
            continue
        old = ast.parse(prior.stdout)
        current = ast.parse((ROOT / name).read_bytes()) if (ROOT / name).is_file() else ast.Module(body=[])
        old_tests = {n.name for n in ast.walk(old) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')}
        current_tests = {n.name for n in ast.walk(current) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')}
        removed = sorted(old_tests - current_tests)
        test_changes.append({'file': name, 'previous_tests': len(old_tests), 'removed': removed})
        if removed:
            issues.append('OLD_TEST_REMOVED:' + name)
    paths = {ROOT / p for p in changed if (ROOT / p).is_file()}
    paths.add(RECORDS / '实施报告.md')
    records = []
    for record in sorted(EVIDENCE.glob('*.json')):
        value = json.loads(record.read_text())
        output = value.get('output') or value.get('log')
        expected = value.get('output_sha256') or value.get('log_sha256')
        if output:
            path = Path(output)
            if not path.is_absolute():
                path = EVIDENCE / path
            valid = path.is_file() and expected == hashlib.sha256(path.read_bytes()).hexdigest()
            if not valid:
                issues.append('EVIDENCE_HASH_MISMATCH:' + record.name)
            records.append({'record': record.name, 'exit_code': value.get('exit_code'),
                            'head': value.get('head'), 'output_bound': valid})
        paths.add(record)
    paths.update(p for p in EVIDENCE.rglob('*') if p.is_file())
    patterns = {**SECRET_PATTERNS,
        'age-secret': re.compile(rb'AGE-SECRET-KEY-1[0-9A-Z]{50,}'),
        'generated-credential': re.compile(rb'\bsynthetic-[0-9a-f]{64}\b')}
    from data_security.tests.synthetic import samples
    payloads = [sample.text.encode() for sample in samples()]
    hygiene, source_hashes = [], {}
    for path in sorted(paths):
        data = path.read_bytes()
        if path.is_symlink():
            hygiene.append({'file': str(path), 'code': 'SYMLINK'})
        if path.is_relative_to(EVIDENCE) and path.stat().st_mode & 0o077:
            hygiene.append({'file': str(path), 'code': 'EVIDENCE_PERMISSIONS'})
        for name, pattern in patterns.items():
            if pattern.search(data):
                hygiene.append({'file': str(path), 'code': name})
        if any(payload in data for payload in payloads):
            hygiene.append({'file': str(path), 'code': 'KNOWN_CORPUS_PLAINTEXT'})
        if path.is_relative_to(ROOT):
            source_hashes[str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
    if EVIDENCE.stat().st_mode & 0o077 or hygiene:
        issues.append('EVIDENCE_HYGIENE')
    mapping = json.loads((RECORDS / 'sessions/phase-05.json').read_text())
    execution = watchdog.process(mapping.get('pid'))
    supervisor = watchdog.process(mapping.get('watchdog_pid'))
    active = (execution is not None and supervisor is not None and
              execution['start_ticks'] == mapping.get('pid_start_ticks') and
              supervisor['start_ticks'] == mapping.get('watchdog_start_ticks') and
              mapping.get('supervision_state') == 'running')
    if not active:
        issues.append('SUPERVISION_NOT_RUNNING')
    print(json.dumps({'version': 'ds.phase5.observation.v1', 'head': head, 'branch': branch,
        'worktree_dirty': bool(git('status', '--porcelain')), 'ancestors': ancestors,
        'main_worktree': main_state, 'frozen_changes': frozen, 'old_test_changes': test_changes,
        'checked_python_files': count,
        'dependency_violations': [{'file': f.file, 'line': f.line, 'code': f.code} for f in findings],
        'source_hashes': source_hashes, 'evidence_records': records, 'hygiene': hygiene,
        'supervision': {'active': active, 'session_id': mapping['session_id'],
                        'checked_at': mapping.get('checked_at'), 'pid': mapping.get('pid'),
                        'watchdog_pid': mapping.get('watchdog_pid')},
        'independent_acceptance': False, 'next_phase_authorized': False, 'issues': issues}, ensure_ascii=False))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
