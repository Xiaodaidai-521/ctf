"""Read-only E3 metadata audit; development observations never authorize completion."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from tools.data_security import dependencies, watchdog
from tools.data_security.isolation import ROOT
from tools.data_security.verify_phase1 import git, SECRET_PATTERNS

BASELINE = '65ef487fab356dfd0eddaa4e3cef29bf85d44558'
RECORDS = Path('/home/hatch/workspace/data-security-seven-phases')
EVIDENCE = RECORDS / 'evidence/phase-03'
MAPPING = RECORDS / 'sessions/phase-03.json'
# Pinned by this phase's E3/preflight-records.json, not an E2 acceptance result.
MAIN = Path('/home/hatch/workspace/ctf-repo')
MAIN_HEAD = 'be67a4e59d4a28ab07f3a55b295081c5831acaaa'
MAIN_BRANCH = 'fix/event-id-over-64'

SOURCE_PATHS = frozenset({
    'backend/agents/context/student_profile_adapter.py', 'backend/agents/context/teaching_context.py',
    'backend/agents/specialists/knowledge_agent.py', 'backend/agents/specialists/knowledge_diagnosis_agent.py',
    'backend/agents/specialists/study_strategy_agent.py', 'backend/ai_assistant/prompt_budget.py',
    'backend/ai_assistant/security.py', 'backend/ai_assistant/service.py', 'backend/ai_assistant/views.py',
    'backend/ai_providers/__init__.py', 'backend/ai_providers/base.py',
    'backend/ai_providers/deepseek.py', 'backend/ai_providers/moonshot.py',
    'backend/ai_providers/qwen.py', 'backend/ai_providers/spark.py',
    'backend/ai_providers/volcano.py', 'backend/ai_providers/wenxin.py',
    'backend/audit/__init__.py', 'backend/audit/apps.py', 'backend/audit/admin.py',
    'backend/audit/bridge.py', 'backend/audit/middleware.py', 'backend/audit/models.py',
    'backend/audit/services.py', 'backend/audit/serializers.py', 'backend/audit/views.py',
    'backend/audit/urls.py', 'backend/audit/migrations/0004_securityauditrecord.py',
    'backend/challenges/container_manager.py', 'backend/challenges/coze_injector.py',
    'backend/challenges/frp_client_manager.py', 'backend/challenges/views.py',
    'backend/ctf_backend/apps.py', 'backend/ctf_backend/security_bootstrap.py',
    'backend/ctf_backend/settings.py', 'backend/ctf_backend/wsgi.py', 'backend/ctfsafe/encryption.py',
    'backend/export_risk/decisions/outbox.py', 'backend/legal/services/compliance_agent.py',
    'backend/legal_kb/services/embedding_service.py', 'backend/legal_kb/services/rag_answer_service.py',
    'backend/manage.py', 'backend/nginx.conf', 'backend/start.sh',
    'backend/users/management/commands/bootstrap_teacher.py', 'backend/users/serializers.py',
    'backend/users/views.py', 'docker-compose.yml', 'frontend/nginx.conf', 'frp/frps.ini',
    'backend/data_security/application/policy_catalog.py', 'backend/data_security/application/audit_gateway.py',
    'backend/data_security/adapters/keys.py', 'backend/data_security/adapters/persistence/__init__.py',
    'backend/data_security/adapters/persistence/policies.py', 'backend/data_security/adapters/persistence/audit.py',
    'backend/data_security/adapters/persistence/backup.py', 'backend/data_security/adapters/llm/__init__.py',
    'backend/data_security/adapters/llm/official.py', 'backend/data_security/adapters/django/authentication.py',
    'backend/data_security/adapters/django/logging.py', 'backend/data_security/adapters/django/content.py',
    'backend/data_security/adapters/django/execution.py', 'backend/data_security/tests/phase3_fixtures.py',
    'docs/data-security/phase3-policy.json', 'docs/data-security/contracts.md',
    'docs/data-security/operations.md', 'docs/data-security/acceptance.md',
    'tools/data_security/dependencies.py', 'tools/data_security/phase-boundary.json',
    'tools/data_security/verify_phase3.py',
})
TEST_DIRECTORIES = frozenset({
    'backend/data_security/tests', 'backend/audit', 'backend/users', 'backend/ai_assistant',
    'backend/agents/tests', 'backend/ai_providers/tests', 'backend/legal/tests',
    'backend/legal_kb/tests', 'backend/rag_ingestion/tests', 'backend/export_risk/tests',
})


def allowed(path):
    target = Path(path)
    return (path in SOURCE_PATHS or
            target.parent.as_posix() in TEST_DIRECTORIES and
            re.fullmatch(r'test_phase3_[a-z0-9_]+\.py', target.name) is not None or
            target.parent.as_posix() == 'tools/data_security' and
            re.fullmatch(r'phase3_[a-z0-9_]+\.py', target.name) is not None)


def main():
    if Path.cwd() != ROOT or ROOT != Path('/home/hatch/workspace/ctf-data-security'):
        raise RuntimeError('ISOLATED_WORKTREE_REQUIRED')
    sys.path.insert(0, str(ROOT / 'backend'))
    from data_security.tests.synthetic import samples
    from data_security.tests.phase2_fixtures import root_key, KeyPurpose

    observed_at = datetime.now(timezone.utc)
    issues = []
    head, branch = git('rev-parse', 'HEAD'), git('branch', '--show-current')
    original = set(git('ls-tree', '-r', '--name-only', BASELINE).splitlines())
    changed = set(git('diff', '--name-only', BASELINE).splitlines())
    changed.update(git('ls-files', '--others', '--exclude-standard').splitlines())
    changed.discard('')
    frozen_changes = sorted(p for p in changed if p.startswith('backend/data_security/contracts/') or
        p in original and (p.endswith('.py') and dependencies.owner(dependencies.module_name(p)) == 'M0' or
                          'tests' in Path(p).parts or Path(p).name == 'tests.py' or
                          Path(p).name.startswith('test_') or '.test.' in Path(p).name or '.spec.' in Path(p).name))
    outside_general_scope = sorted(p for p in changed if not allowed(p))
    declaration_test = 'backend/data_security/tests/test_phase2_boundaries.py'
    prior_test = subprocess.check_output(['git', 'show', BASELINE + ':' + declaration_test], cwd=ROOT)
    prior_line = b'        count, violations = scan(ROOT, phase=2)\n'
    expected_test = prior_test.replace(prior_line, b'        count, violations = scan(ROOT, phase=3)\n', 1)
    declaration_matches_approval = (prior_test.count(prior_line) == 1 and
        (ROOT / declaration_test).read_bytes() == expected_test)
    # R records the user's 2026-11-05 15:36 one-line approval. Keep the
    # changed file visible; compare its entire bytes, never exempt it from scan.
    scope_matches_approval = (frozen_changes == [declaration_test] and
        outside_general_scope == [declaration_test] and declaration_matches_approval)
    ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', BASELINE, head],
                              cwd=ROOT, capture_output=True).returncode == 0
    if not scope_matches_approval or not ancestor or branch != 'feat/data-security':
        issues.append('WORKTREE_SCOPE')
    main_state = {'head': git('rev-parse', 'HEAD', root=MAIN),
                  'branch': git('branch', '--show-current', root=MAIN),
                  'dirty': bool(git('status', '--porcelain', '--untracked-files=all', root=MAIN))}
    if main_state != {'head': MAIN_HEAD, 'branch': MAIN_BRANCH, 'dirty': False}:
        issues.append('MAIN_BASELINE_CHANGED')
    checked, dependency_findings = dependencies.scan(ROOT, phase=3)
    if dependency_findings:
        issues.append('DEPENDENCIES')
    declaration = ROOT / 'tools/data_security/phase-boundary.json'
    try:
        declared_phase = json.loads(declaration.read_bytes())
    except (OSError, ValueError):
        declared_phase = None
    if declaration.is_symlink() or declared_phase != {'phase': 3, 'version': 'phase-boundary.v1'}:
        issues.append('PHASE_DECLARATION')

    payloads = [sample.text.encode() for sample in samples()]
    for label in ('data', 'other', *(purpose.value for purpose in KeyPurpose)):
        payloads.extend((root_key(label), root_key(label).hex().encode()))
    patterns = {**SECRET_PATTERNS,
        'phase3-generated-credential': re.compile(rb'\bsynthetic-[0-9a-f]{64}\b'),
        'age-secret-identity': re.compile(rb'\bAGE-SECRET-KEY-1[0-9A-Z]{50,}\b'),
        'bearer-credential-shaped': re.compile(rb'\bBearer[ \t]+[A-Za-z0-9_.~+/-]{32,}={0,2}'),
    }
    source_manifest, evidence_manifest, runtime_manifest, hygiene, records, bindings = {}, [], [], [], [], []
    paths = set()
    for relative in sorted(changed):
        source = ROOT / relative
        if source.is_symlink():
            hygiene.append({'file': relative, 'code': 'SOURCE_SYMLINK'})
        elif source.is_file():
            paths.add(source)
        else:
            source_manifest[relative] = {'deleted': True, 'sha256': None}
    if not EVIDENCE.is_dir() or EVIDENCE.is_symlink():
        issues.append('EVIDENCE_DIRECTORY_MISSING_OR_SYMLINK')
    else:
        for path in (EVIDENCE, *EVIDENCE.rglob('*')):
            if path.is_symlink():
                hygiene.append({'file': str(path), 'code': 'EVIDENCE_SYMLINK'})
            elif path.is_dir():
                if path.stat().st_mode & 0o077:
                    hygiene.append({'file': str(path), 'code': 'EVIDENCE_DIRECTORY_PERMISSIONS'})
            elif path.is_file():
                paths.add(path)
    paths.update(path for path in (RECORDS / 'logs').iterdir()
                 if path.is_file() and re.search(r'phase-?0?3', path.name))
    paths.update((ROOT / '.state/pg-run').glob('*.log'))
    # The report is observed, never edited. SDK transcripts spanning earlier
    # phases are not product run logs; only their supervision cursor is checked.
    paths.add(RECORDS / '实施报告.md')
    paths.add(MAPPING)
    if MAPPING.with_suffix('.control.json').exists():
        paths.add(MAPPING.with_suffix('.control.json'))
    hashes = {}
    for path in sorted(paths):
        if path.is_symlink():
            hygiene.append({'file': str(path), 'code': 'SYMLINK'})
            continue
        if not path.is_file():
            hygiene.append({'file': str(path), 'code': 'MISSING_OBSERVED_FILE'})
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        hashes[path] = digest
        mode = path.stat().st_mode & 0o777
        if path.parent in (RECORDS / 'logs', ROOT / '.state/pg-run'):
            runtime_manifest.append({'file': str(path), 'sha256': digest, 'bytes': len(data), 'mode': oct(mode)})
        if any(value in data for value in payloads):
            hygiene.append({'file': str(path), 'code': 'KNOWN_SYNTHETIC_VALUE'})
        for name, pattern in patterns.items():
            if pattern.search(data):
                hygiene.append({'file': str(path), 'code': name})
        if path.is_relative_to(ROOT) and path.relative_to(ROOT).as_posix() in changed:
            source_manifest[path.relative_to(ROOT).as_posix()] = {
                'sha256': digest, 'bytes': len(data), 'mode': oct(mode), 'deleted': False}
        if not path.is_relative_to(EVIDENCE):
            continue
        evidence_manifest.append({'file': str(path), 'sha256': digest, 'bytes': len(data), 'mode': oct(mode),
                                  'unsealed_log': path.suffix == '.log' and not path.with_suffix('.json').is_file()})
        if mode & 0o077:
            hygiene.append({'file': str(path), 'code': 'EVIDENCE_PERMISSIONS'})
        if path.suffix != '.json':
            continue
        try:
            record = json.loads(data)
        except ValueError:
            hygiene.append({'file': str(path), 'code': 'INVALID_EVIDENCE_JSON'})
            continue
        # Preserve every nested exit/return code without copying command args,
        # raw exception text, payloads, or old preflight stdout into this report.
        stack, codes = [record], []
        while stack:
            item = stack.pop()
            if type(item) is dict:
                for key in ('exit_code', 'returncode'):
                    if key in item:
                        if type(item[key]) is int:
                            codes.append(item[key])
                        else:
                            hygiene.append({'file': str(path), 'code': 'INVALID_EXIT_CODE'})
                stack.extend(value for value in item.values() if type(value) in (dict, list))
            elif type(item) is list:
                stack.extend(item)
        if codes:
            records.append({'file': str(path), 'exit_codes': codes, 'has_nonzero': any(code != 0 for code in codes)})
        if type(record) is dict:
            output = record.get('output', record.get('log'))
            expected = record.get('output_sha256', record.get('log_sha256'))
            if output is None and 'log_sha256' in record:
                output = path.with_suffix('.log').name
            if output is not None:
                if type(output) is not str:
                    hygiene.append({'file': str(path), 'code': 'INVALID_OUTPUT_REFERENCE'})
                    continue
                target = Path(output)
                target = target if target.is_absolute() else EVIDENCE / target
                if not target.is_relative_to(EVIDENCE) or '..' in target.parts or target.is_symlink():
                    hygiene.append({'file': str(path), 'code': 'OUTPUT_REFERENCE_ESCAPE'})
                    continue
                bindings.append((path, target, expected))
    links = []
    for record, target, expected in bindings:
        actual = hashes.get(target)
        matched = (type(expected) is str and re.fullmatch(r'[0-9a-f]{64}', expected) is not None
                   and actual is not None and expected == actual)
        links.append({'file': str(record), 'output': str(target), 'sha256': actual,
                      'recorded_hash_present': expected is not None, 'recorded_hash_matches': matched})
        if actual is None:
            hygiene.append({'file': str(record), 'code': 'MISSING_EVIDENCE_OUTPUT'})
        elif expected is not None and not matched:
            hygiene.append({'file': str(record), 'code': 'EVIDENCE_HASH_MISMATCH'})
    if hygiene:
        issues.append('HYGIENE_OR_EVIDENCE_INTEGRITY')

    supervision = {'mapping': str(MAPPING), 'mapping_sha256': hashes.get(MAPPING),
                   'observation_valid': False, 'watchdog_live': False, 'single_executor': False,
                   'execution_complete_recorded': False, 'independent_acceptance_recorded': False,
                   'candidate_sha': None, 'next_phase_authorized_by_this_audit': False}
    try:
        config = watchdog.load(MAPPING)
        watchdog.validate(config)
        if (config['phase'] != 3 or config.get('baseline_candidate') != BASELINE or
                config.get('branch') != 'feat/data-security'):
            raise ValueError('WRONG_PHASE_MAPPING')
        candidate = config.get('candidate_sha') or None
        if candidate is not None and (type(candidate) is not str or re.fullmatch(r'[0-9a-f]{40}', candidate) is None):
            raise ValueError('INVALID_CANDIDATE')
        watcher = watchdog.process(config.get('watchdog_pid'))
        executions = watchdog.session_processes(config)
        heartbeat = datetime.fromisoformat(config['checked_at'])
        if heartbeat.tzinfo is None:
            raise ValueError('INVALID_HEARTBEAT')
        age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
        observations = {key: watchdog.observation(config[key], config.get('last_observation', {}).get(key))
                        for key in ('run_log', 'session_record')}
        argv = watcher['argv'] if watcher else []
        mapped = (argv.count('--mapping') == 1 and argv.index('--mapping') + 1 < len(argv) and
                  argv[argv.index('--mapping') + 1] == str(MAPPING) and
                  (str(ROOT / 'tools/data_security/watchdog.py') in argv or 'tools.data_security.watchdog' in argv))
        live = bool(watcher and watcher['start_ticks'] == config.get('watchdog_start_ticks') and
                    watcher['cwd'] == str(ROOT) and mapped and 0 <= age < 120 and
                    len(executions) == 1 and watcher['pid'] != executions[0]['pid'] and
                    config.get('operator_state') == 'active' and
                    all(value['exists'] and not value['blocked'] and not value['pending'] for value in observations.values()))
        complete, accepted = watchdog.report_state((RECORDS / '实施报告.md').read_text(), 3, candidate)
        supervision.update(observation_valid=True, session_id=config['session_id'], candidate_sha=candidate,
            operator_state=config.get('operator_state'), heartbeat_age_seconds=round(age, 3),
            watchdog_pid=watcher['pid'] if watcher else None, watchdog_phase_mapping_matches=mapped,
            watchdog_live=live, single_executor=len(executions) == 1,
            executor_pids=[item['pid'] for item in executions], observations=observations,
            execution_complete_recorded=complete, independent_acceptance_recorded=accepted,
            development_state='in-development-no-candidate' if candidate is None else 'candidate-recorded-not-accepted-by-this-audit')
    except (OSError, ValueError, KeyError, TypeError):
        issues.append('INVALID_OR_MISSING_SUPERVISION')
    if not supervision['watchdog_live']:
        issues.append('G05_NOT_CONFIRMED')

    result = {
        'phase': 3, 'observed_at': observed_at.isoformat(),
        'scope': {'baseline': BASELINE, 'head': head, 'branch': branch, 'baseline_ancestor': ancestor,
                  'outside_general_scope_paths': outside_general_scope, 'frozen_changes': frozen_changes,
                  'old_tests_and_m0_unchanged': not frozen_changes,
                  'approved_declaration_update': {'file': declaration_test,
                      'approval_ref': 'report/phase3-g02-20261105-1536',
                      'exact_baseline_delta_verified': declaration_matches_approval,
                      'scope_matches_approval': scope_matches_approval},
                  'main_read_only': main_state},
        'source_manifest': source_manifest,
        'dependencies': {'phase': 3, 'checked_python_files': checked, 'violations': [
            {'file': item.file, 'line': item.line, 'code': item.code} for item in dependency_findings]},
        'evidence_manifest': evidence_manifest, 'evidence_output_bindings': links,
        'runtime_log_manifest': runtime_manifest,
        'recorded_command_results': records,
        'historical_nonzero_records': sum(item['has_nonzero'] for item in records),
        'history_policy': 'all recorded nonzero exits retained; no inference that a later run supersedes them',
        'hygiene': {'files_checked': len(hashes), 'violations': hygiene,
            'limitation': 'frozen synthetic samples, deterministic phase2 fixture keys and bounded credential shapes only; '
                          'not universal secret discovery or scanning of private key stores/SDK conversation transcripts; '
                          'unsealed/live files are snapshots, not sealed command evidence'},
        'supervision': supervision,
        'issues': sorted(set(issues)),
        'gate_status': 'development metadata observation only; not phase completion, independent acceptance, or authorization',
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
