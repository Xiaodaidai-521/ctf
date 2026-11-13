"""Run repository test groups in separate synthetic databases and retain evidence.

Uses the existing owned local cluster and scrubbed environment. It never loads
the business .env, changes password hashers, or replaces test assertions.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.full_audit.run import clean_env, config_and_identity


def sources():
    result = {}
    for base in (ROOT / 'backend', ROOT / 'tools'):
        for path in base.rglob('*.py'):
            if any(part in {'venv', 'node_modules', '__pycache__'} or part.startswith('.')
                   for part in path.relative_to(base).parts):
                continue
            result[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def execute(label, arguments, evidence, config, settings=None, unit=False, extra_env=None, cwd=None):
    evidence = Path(evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    env = clean_env()
    env.update(FULL_AUDIT_LEGACY='1', FULL_AUDIT_TEST_DB='test_audit_batch_' + label,
               FULL_AUDIT_RESULT=str(evidence / (label + '.json')),
               MAINLINE1_TEST_PORT=str(config['port']),
               FULL_AUDIT_NETWORK_PORT=str(config['port']))
    if settings:
        env['DJANGO_SETTINGS_MODULE'] = settings
    env.update(extra_env or {})
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--entry',
               'unit' if unit else 'django', *arguments]
    started = time.monotonic()
    record = {'command': command, 'synthetic_only': True,
              'test_database': env['FULL_AUDIT_TEST_DB'], 'source_hashes_before': sources()}
    with (evidence / (label + '.log')).open('w', encoding='utf-8') as output:
        process = subprocess.run(command, env=env, cwd=cwd or ROOT / 'backend', stdout=output,
                                 stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    after = sources()
    record.update(exit_code=process.returncode, elapsed_seconds=round(time.monotonic() - started, 2),
                  source_changes=[p for p in record['source_hashes_before'].keys() | after.keys()
                                  if record['source_hashes_before'].get(p) != after.get(p)])
    (evidence / (label + '-command.json')).write_text(
        json.dumps(record, indent=2), encoding='utf-8')
    result_path = evidence / (label + '.json')
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding='utf-8'))
        record['counts'] = {'tests': result['tests'], **{
            key: len(result[key]) for key in ('passed', 'failures', 'errors', 'skipped')}}
    print(json.dumps({'label': label, **{k: v for k, v in record.items()
                                       if k not in ('source_hashes_before', 'command')}}), flush=True)
    return label, record


def entry(kind, arguments):
    # Permit only the owned database and loopback servers bound by this process.
    # A test cannot reach a model provider, Docker daemon, or an unrelated server.
    import socket
    port = int(os.environ['FULL_AUDIT_NETWORK_PORT'])
    listeners = []
    def fence(event, args):
        if event == 'socket.bind':
            sock, address = args
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', 'localhost', '::1'):
                listeners.append(sock)
        elif event == 'socket.connect':
            sock, address = args
            allowed = isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1') and address[1] == port
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
                for listener in listeners:
                    try:
                        allowed = allowed or listener.getsockname()[1] == address[1]
                    except OSError:
                        pass
            if not allowed:
                raise RuntimeError('FULL_AUDIT_EXTERNAL_CONNECTION_FORBIDDEN')
        elif event == 'socket.getaddrinfo' and args[0] not in ('localhost', '127.0.0.1', '::1', None):
            raise RuntimeError('FULL_AUDIT_EXTERNAL_DNS_FORBIDDEN')
    sys.addaudithook(fence)
    if kind == 'django':
        from django.core.management import execute_from_command_line
        execute_from_command_line(['audit', *arguments])
    else:
        import unittest
        from tools.full_audit.runner import AuditResult, write_result
        from ctf_backend.security_bootstrap import bind_legacy_for_tests
        from data_security.contracts import Environment
        bind_legacy_for_tests(environment=Environment.TEST)
        program = unittest.main(module=None, argv=['audit', *arguments], exit=False,
            testRunner=unittest.TextTestRunner(verbosity=2, resultclass=AuditResult))
        write_result(program.result)
        raise SystemExit(not program.result.wasSuccessful())


def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--entry':
        entry(sys.argv[2], sys.argv[3:])
        return
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--targets', nargs='+')
    args = parser.parse_args()
    evidence = Path(args.evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    config = config_and_identity()
    targets = args.targets or ['data_security', 'resources', 'audit', 'agent_memory', 'agent_runtime',
        'agents', 'ai_assistant', 'announcements', 'articles', 'challenges', 'ctf_backend', 'data_lab',
        'evaluation_center', 'exams', 'export_quota', 'export_risk', 'feedback_center',
        'learning_analytics', 'learning_knowledge', 'learning_map', 'learning_paths', 'legal',
        'legal_kb', 'practical_training', 'rag_ingestion', 'scripts', 'skill_review',
        'student_profiles', 'submissions', 'test_auth', 'users']
    (evidence / 'manifest.json').write_text(json.dumps({
        'targets': targets, 'workers': args.workers, 'synthetic_only': True,
        'original_password_hashers': True, 'legacy_test_binding': True,
        'external_network_forbidden': True, 'sources': sources()}, indent=2), encoding='utf-8')
    records = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute, target, ['test', target, '--noinput', '--verbosity', '1'],
                               evidence, config) for target in targets]
        for future in as_completed(futures):
            label, record = future.result()
            records[label] = record
            (evidence / 'progress.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    raise SystemExit(any(record['exit_code'] for record in records.values()))


if __name__ == '__main__':
    main()
