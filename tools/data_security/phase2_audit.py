"""Metadata-only phase-2 scope, evidence hygiene and live supervision audit."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess

from tools.data_security import watchdog
from tools.data_security.isolation import ROOT
from tools.data_security.verify_phase1 import git, SECRET_PATTERNS
from data_security.tests.synthetic import samples
from data_security.tests.phase2_fixtures import root_key, KeyPurpose

BASELINE = '2970a4cb18103b8de4ac7f04a4ea1aa6322b5989'
MAIN_HEAD = 'be67a4e59d4a28ab07f3a55b295081c5831acaaa'
RECORDS = Path('/home/hatch/workspace/data-security-seven-phases')
EVIDENCE = RECORDS / 'evidence/phase-02'
LEGACY = {'backend/mainline1/rules.py', 'backend/ai_assistant/security.py', 'backend/legal/services/fact_redactor.py'}
OLD_ALLOWED = LEGACY | {'tools/data_security/dependencies.py', 'tools/data_security/watchdog.py',
    'docs/data-security/contracts.md', 'docs/data-security/acceptance.md', 'docs/data-security/operations.md'}


def allowed(path):
    return path in OLD_ALLOWED or path == 'backend/ctf_backend/security_bootstrap.py' or path.startswith((
        'backend/data_security/core/', 'backend/data_security/application/', 'backend/data_security/adapters/',
        'backend/data_security/tests/phase2_', 'backend/data_security/tests/test_phase2_',
        'tools/data_security/phase2_', 'tools/data_security/verify_phase2.', 'tools/data_security/phase-boundary.'))


def main():
    assert Path.cwd() == ROOT == Path('/home/hatch/workspace/ctf-data-security')
    issues = []
    head = git('rev-parse', 'HEAD')
    changed = set(git('diff', '--name-only', BASELINE).splitlines())
    changed.update(git('ls-files', '--others', '--exclude-standard').splitlines())
    changed.discard('')
    original = set(git('ls-tree', '-r', '--name-only', BASELINE).splitlines())
    invalid = sorted(p for p in changed if not allowed(p) or p in original and p not in OLD_ALLOWED)
    ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', BASELINE, head], cwd=ROOT).returncode == 0
    main_root = Path('/home/hatch/workspace/ctf-repo')
    main_state = {'head': git('rev-parse', 'HEAD', root=main_root),
                  'status': git('status', '--porcelain', '--untracked-files=all', root=main_root)}
    if invalid or not ancestor or git('branch', '--show-current') != 'feat/data-security':
        issues.append('SCOPE')
    if main_state != {'head': MAIN_HEAD, 'status': ''}:
        issues.append('MAIN_CHANGED')
    payloads = [s.text.encode() for s in samples()]
    payloads += [root_key(label).hex().encode() for label in ('data', 'other', *(p.value for p in KeyPurpose))]
    # The current command log is still being written; seal it in the next audit.
    paths = set(p for p in EVIDENCE.iterdir() if p.is_file() and
                (p.suffix != '.log' or p.with_suffix('.json').is_file()))
    paths.update(ROOT / p for p in changed if (ROOT / p).is_file())
    paths.add(RECORDS / '实施报告.md')
    paths.update(p for p in (RECORDS / 'logs').glob('*phase-02*') if p.is_file())
    paths.update(p for p in (RECORDS / 'logs').glob('*phase2*') if p.is_file())
    paths.update(p for p in (ROOT / '.state/pg-run').glob('*.log') if p.is_file())
    violations, commands, manifest = [], [], []
    for path in sorted(paths):
        if path.is_symlink():
            violations.append({'file': str(path), 'code': 'SYMLINK'})
            continue
        data = path.read_bytes()
        if any(value in data for value in payloads):
            violations.append({'file': str(path), 'code': 'SYNTHETIC_VALUE'})
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                violations.append({'file': str(path), 'code': name})
        if path.parent == EVIDENCE:
            if path.stat().st_mode & 0o077:
                issues.append('EVIDENCE_PERMISSIONS')
            manifest.append({'file': path.name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
            if path.suffix == '.json':
                record = json.loads(data)
                if isinstance(record, dict) and 'command' in record:
                    output = Path(record['output'])
                    if output.parent != EVIDENCE or hashlib.sha256(output.read_bytes()).hexdigest() != record['output_sha256']:
                        issues.append('HASH_MISMATCH')
                    commands.append({k: record[k] for k in ('label', 'head', 'exit_code', 'output_sha256')})
    if EVIDENCE.stat().st_mode & 0o077:
        issues.append('EVIDENCE_DIRECTORY_PERMISSIONS')
    if violations:
        issues.append('EVIDENCE_HYGIENE')
    config = watchdog.load(RECORDS / 'sessions/phase-02.json')
    process = watchdog.process(config.get('watchdog_pid'))
    executions = watchdog.session_processes(config)
    heartbeat = config.get('checked_at')
    fresh = False
    if heartbeat:
        fresh = 0 <= (datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat)).total_seconds() < 120
    live = bool(process and process['start_ticks'] == config.get('watchdog_start_ticks') and
                process['cwd'] == str(ROOT) and len(executions) == 1 and fresh)
    if not live:
        issues.append('WATCHDOG_NOT_LIVE')
    complete, accepted = watchdog.report_state((RECORDS / '实施报告.md').read_text(), 2, config.get('candidate_sha'))
    print(json.dumps({'baseline': BASELINE, 'head': head, 'baseline_ancestor': ancestor,
        'main_read_only': main_state, 'invalid_paths': invalid, 'old_tests_and_m0_unchanged': not any(
            p in original and (p.startswith('backend/data_security/contracts/') or '/test' in p) for p in changed),
        'source_manifest': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sorted(changed)},
        'commands': commands, 'evidence_manifest': manifest, 'hygiene': {'files': len(paths), 'violations': violations,
            'limitation': 'known synthetic values and bounded credential shapes, not universal secret discovery'},
        'supervision': {'sid': config['session_id'], 'watchdog_live': live, 'heartbeat': heartbeat,
            'executors': len(executions), 'operator_state': config['operator_state'],
            'execution_complete': complete, 'independent_acceptance': accepted,
            'next_phase_allowed': complete and accepted},
        'versions': {name: importlib.metadata.version(name) for name in ('cryptography', 'Django', 'psycopg2-binary')},
        'issues': sorted(set(issues))}, ensure_ascii=False, indent=2))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
