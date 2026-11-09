"""Read-only scope, inventory and evidence audit. Emits metadata, never sample values."""
from collections import Counter
from dataclasses import fields
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from tools.data_security.isolation import EVIDENCE, ROOT
from tools.data_security import watchdog

BASE = 'be67a4e59d4a28ab07f3a55b295081c5831acaaa'
MAIN = Path('/home/hatch/workspace/ctf-repo')
RECORDS = EVIDENCE.parents[1]
REPORT = RECORDS / '实施报告.md'
ALLOWED_FILES = {'.gitignore', 'backend/data_security/__init__.py', 'tools/__init__.py',
                 'docs/data-security/contracts.md', 'docs/data-security/operations.md',
                 'docs/data-security/acceptance.md'}
ALLOWED_PREFIXES = ('backend/data_security/contracts/', 'backend/data_security/tests/', 'tools/data_security/')
SECRET_PATTERNS = {
    'generated-test-credential': re.compile(rb'DS_TEST_ONLY_[0-9a-f]{64}'),
    'private-key-block': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{40,}'),
    'credential-url': re.compile(rb'https?://[^\s/@:]{1,100}:[^\s/@]{1,200}@'),
    'provider-key-shaped': re.compile(rb'\bsk-[A-Za-z0-9_-]{32,}\b'),
}


def git(*args, root=ROOT):
    return subprocess.check_output(['git', *args], cwd=root,
        env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'), text=True).strip()


def allowed(path):
    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES)


def main():
    if ROOT != Path('/home/hatch/workspace/ctf-data-security') or Path.cwd() != ROOT:
        raise RuntimeError('ISOLATED_WORKTREE_REQUIRED')
    sys.path.insert(0, str(ROOT / 'backend'))
    from data_security.contracts import BASELINE_LIMITS, CONTRACT_TYPES, CONTRACT_VERSION, PORT_TYPES, Outlet
    from data_security.tests.synthetic import dataset_fingerprint, samples

    issues = []
    head = git('rev-parse', 'HEAD')
    branch = git('branch', '--show-current')
    original = set(git('ls-tree', '-r', '--name-only', BASE).splitlines())
    changed = set(git('diff', '--name-only', BASE).splitlines())
    changed.update(git('ls-files', '--others', '--exclude-standard').splitlines())
    invalid_paths = sorted(path for path in changed if path and not allowed(path))
    legacy_changes = sorted(changed.intersection(original) - {'.gitignore'})
    ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, head], cwd=ROOT).returncode == 0
    main_state = {'head': git('rev-parse', 'HEAD', root=MAIN),
                  'branch': git('branch', '--show-current', root=MAIN),
                  'status': git('status', '--porcelain', '--untracked-files=all', root=MAIN)}
    if branch != 'feat/data-security' or not ancestor or invalid_paths or legacy_changes:
        issues.append('WORKTREE_SCOPE')
    if main_state != {'head': BASE, 'branch': 'fix/event-id-over-64', 'status': ''}:
        issues.append('MAIN_BASELINE_CHANGED')

    docs = ROOT / 'docs/data-security'
    operations = (docs / 'operations.md').read_text()
    cids = re.findall(r'^\| (C\d\d) \|', operations, re.M)
    dids = re.findall(r'^\| (D\d+) \|', operations, re.M)
    if cids != [f'C{i:02d}' for i in range(1, 17)] or dids != [f'D{i}' for i in range(1, 17)]:
        issues.append('REGISTER_INCOMPLETE')
    for name in ('contracts.md', 'operations.md', 'acceptance.md'):
        if not (docs / name).is_file():
            issues.append('DOCUMENT_MISSING')

    dataset = samples()
    family_counts = Counter((item.category.value, item.positive) for item in dataset if item.teaching is None)
    teaching_counts = Counter(item.teaching for item in dataset if item.teaching is not None)
    patterns = [item.text.encode('utf-8') for item in dataset]
    commands = []
    paths = list(EVIDENCE.glob('*')) + list(docs.glob('*.md')) + [REPORT]
    paths += [path for path in (RECORDS / 'logs').glob('*phase-01*') if path.is_file()]
    paths += [ROOT / path for path in changed if path and allowed(path) and (ROOT / path).is_file()]
    # Include isolated server/test logs, not database contents or downloaded packages.
    paths += [path for path in (ROOT / '.state/pg-run').glob('*.log') if path.is_file()]
    violations = []
    audited = 0
    for path in sorted(set(paths)):
        if not path.is_file() or path.is_symlink():
            if path.is_symlink():
                violations.append({'file': str(path), 'code': 'EVIDENCE_SYMLINK'})
            continue
        data = path.read_bytes()
        audited += 1
        # Fixtures in source are intentionally generated in memory, not copied values.
        if any(sample in data for sample in patterns):
            violations.append({'file': str(path), 'code': 'SYNTHETIC_PAYLOAD_PRESENT'})
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                violations.append({'file': str(path), 'code': label})
        if path.parent == EVIDENCE and path.suffix == '.json':
            try:
                record = json.loads(data)
            except ValueError:
                issues.append('INVALID_EVIDENCE_JSON')
                continue
            if isinstance(record, dict) and 'command' in record:
                output = Path(record['output'])
                matches = output.parent == EVIDENCE and output.is_file() and hashlib.sha256(output.read_bytes()).hexdigest() == record['output_sha256']
                if not matches:
                    issues.append('EVIDENCE_HASH_MISMATCH')
                commands.append({key: record.get(key) for key in
                                 ('label', 'command', 'cwd', 'head', 'exit_code', 'output_sha256')})
        if path.parent == EVIDENCE and path.stat().st_mode & 0o077:
            issues.append('EVIDENCE_PERMISSIONS')
    if violations:
        issues.append('PAYLOAD_OR_SECRET_SHAPE_IN_EVIDENCE')
    if EVIDENCE.stat().st_mode & 0o077:
        issues.append('EVIDENCE_DIRECTORY_PERMISSIONS')

    source_hashes = {}
    for path in sorted(changed):
        target = ROOT / path
        if path and allowed(path) and target.is_file():
            source_hashes[path] = hashlib.sha256(target.read_bytes()).hexdigest()
    config = watchdog.load(RECORDS / 'sessions/phase-01.json')
    watcher = watchdog.process(config.get('watchdog_pid'))
    executions = watchdog.session_processes(config)
    supervised = (watcher is not None and watcher['start_ticks'] == config.get('watchdog_start_ticks')
                  and watcher['cwd'] == str(ROOT) and len(executions) == 1)
    if not supervised:
        issues.append('WATCHDOG_NOT_CONNECTED')
    complete, accepted = watchdog.report_state(REPORT.read_text(), 1, config.get('candidate_sha'))
    print(json.dumps({
        'scope': {'baseline': BASE, 'head': head, 'branch': branch, 'contains_baseline': ancestor,
                  'main_read_only_state': main_state, 'invalid_paths': invalid_paths,
                  'legacy_source_changes': legacy_changes, 'changed_file_sha256': source_hashes},
        'registers': {'coupling_ids': cids, 'decision_ids': dids, 'migration_status': 'not started'},
        'contracts': {'version': CONTRACT_VERSION, 'types': [
            {'name': cls.__name__, 'schema': cls.SCHEMA, 'fields': [field.name for field in fields(cls)],
             'server_only': cls.SERVER_ONLY, 'sensitive': cls.SENSITIVE} for cls in CONTRACT_TYPES],
            'ports': [cls.__name__ for cls in PORT_TYPES], 'limits': BASELINE_LIMITS.to_wire()},
        'dataset': {'version': 'synthetic-2026-11-04.v1', 'count': len(dataset),
                    'sha256': dataset_fingerprint(), 'family_counts': [
                        {'category': category, 'positive': positive, 'count': count}
                        for (category, positive), count in sorted(family_counts.items())],
                    'teaching_counts': dict(teaching_counts), 'payloads_persisted': False},
        'metrics': [{'outlet': outlet.value, 'version': 'ds.metrics.v1', 'measurement': None,
                     'reason': 'phase1-contract-only; no detector or outlet implementation',
                     'enabled_outlets_accepted': 0, 'supported_set_leak_target': 0} for outlet in Outlet],
        'commands': commands,
        'environment_packages': sorted([{'name': d.metadata['Name'], 'version': d.version}
                                       for d in importlib.metadata.distributions()], key=lambda item: item['name'].lower()),
        'evidence_audit': {'files_checked': audited, 'violations': violations,
                           'limitation': 'bounded known-fixture and credential-shape check, not proof against every possible secret'},
        'supervision': {'session_id': config['session_id'], 'watchdog_connected': supervised,
                        'operator_state': config['operator_state'], 'execution_complete': complete,
                        'independent_acceptance': accepted},
        'issues': sorted(set(issues)),
        'gate_status': 'G02 blocked independently; this command cannot authorize completion',
    }, ensure_ascii=False, indent=2))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
