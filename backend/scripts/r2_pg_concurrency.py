"""Real PostgreSQL, independent-process module-five idempotency acceptance.

Run only against the disposable module5_r2 database on 127.0.0.1:55465.
HTTP challenge responses are fixtures, not live Juice Shop/isolation evidence.
No database/transaction/verifier implementation is mocked. APIClient invokes
real views in separate OS processes; a real TCP HTTP fixture supplies state.
"""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
EVIDENCE = ROOT / 'evidence' / 'module5'
sys.path.insert(0, str(BACKEND))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')


def bootstrap():
    import django
    django.setup()
    from django.conf import settings
    from django.db import connection
    db = settings.DATABASES['default']
    assert db['ENGINE'] == 'django.db.backends.postgresql', db
    assert db['HOST'] == '127.0.0.1' and str(db['PORT']) == '55465', db
    assert db['NAME'] == 'module5_r2', db
    assert connection.vendor == 'postgresql'
    assert connection.features.has_select_for_update
    settings.PRACTICAL_TRAINING_ENABLED = True
    settings.PRACTICAL_TRAINING_VERIFIER_IP = '127.0.0.1'
    settings.JUICE_SHOP_PORT_MIN = 58165
    settings.JUICE_SHOP_PORT_MAX = 58165


def json_write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + '\n')


def trace_sql(execute, sql, params, many, context):
    started = time.monotonic()
    try:
        return execute(sql, params, many, context)
    finally:
        print(json.dumps({'sql': sql, 'params': params, 'duration_s': time.monotonic() - started},
                         ensure_ascii=False, default=str), flush=True)


def worker(args):
    bootstrap()
    from django.db import connection, OperationalError, connections
    from rest_framework.test import APIClient
    from users.models import CTFUser
    client = APIClient()
    client.force_authenticate(CTFUser.objects.get(pk=args.student))
    application = 'r2pg-' + args.label
    with connection.cursor() as cur:
        cur.execute('SET application_name = %s', [application])
        cur.execute("SET lock_timeout = '25s'")
        cur.execute('SELECT pg_backend_pid(), current_database(), version()')
        backend_pid, database, version = cur.fetchone()
    data = {'label': args.label, 'os_pid': os.getpid(), 'pg_pid': backend_pid,
            'database': database, 'version': version, 'retries': []}
    try:
        with connection.execute_wrapper(trace_sql):
            for retry in range(5):
                try:
                    started = time.monotonic()
                    response = client.post(args.url, json.loads(args.payload), format='json')
                    if response.status_code in (429, 503):
                        delay = max(1.0, float(response.get('Retry-After', '1')))
                        data['retries'].append({'status': response.status_code, 'delay': delay})
                        time.sleep(delay)
                        continue
                    data.update(status=response.status_code, body=response.data,
                                elapsed_s=time.monotonic() - started)
                    break
                except OperationalError as exc:
                    data['retries'].append({'error': str(exc), 'delay': 1 + retry})
                    connections.close_all()
                    time.sleep(1 + retry)
            else:
                raise AssertionError('Current step did not recover after retries')
    except Exception:
        data['exception'] = traceback.format_exc()
        raise
    finally:
        json_write(EVIDENCE / f'r2-pg-{args.label}-result.json', data)
        connections.close_all()


LOCK_SQL = """SELECT pid, application_name, state, wait_event_type, wait_event,
                        pg_blocking_pids(pid) AS blockers, query
                 FROM pg_stat_activity
                 WHERE application_name LIKE %s ORDER BY pid"""
LOCK_DETAIL_SQL = """SELECT pid, locktype, mode, granted, relation::regclass::text,
                               transactionid::text, page, tuple
                        FROM pg_locks WHERE pid = ANY(%s)
                        ORDER BY pid, locktype, mode"""


def race(name, fixture, assignment, suffix, payloads, monitor):
    from django.db import connection, transaction
    from practical_training.models import LabAssignment
    procs, logs, snapshots = [], [], []
    url = fixture.url(assignment, suffix)
    labels = [f'{name}-{index}' for index in range(2)]

    def observe(phase):
        with monitor.cursor() as cur:
            cur.execute(LOCK_SQL, ['r2pg-' + name + '-%'])
            fields = [item.name for item in cur.description]
            rows = [dict(zip(fields, row)) for row in cur.fetchall()]
            cur.execute(LOCK_DETAIL_SQL, [[row['pid'] for row in rows]])
            lock_fields = [item.name for item in cur.description]
            locks = [dict(zip(lock_fields, row)) for row in cur.fetchall()]
        if any(row['blockers'] for row in rows):
            snapshots.append({'phase': phase, 'at': time.time(), 'activity': rows, 'locks': locks})
        return rows

    try:
        # This is a genuine PostgreSQL row lock, not an in-memory test lock.
        # Both child views must reach their own SELECT FOR UPDATE before release.
        with transaction.atomic():
            LabAssignment.objects.select_for_update().get(pk=assignment.pk)
            with connection.cursor() as cur:
                cur.execute('SELECT pg_backend_pid()')
                holder_pid = cur.fetchone()[0]
            for label, payload in zip(labels, payloads):
                log = (EVIDENCE / f'r2-pg-{label}-sql.log').open('w')
                logs.append(log)
                cmd = [sys.executable, str(Path(__file__).resolve()), '--worker', '--label', label,
                       '--student', str(fixture.student.pk), '--url', url,
                       '--payload', json.dumps(payload, ensure_ascii=False)]
                print('WORKER_COMMAND', json.dumps(cmd, ensure_ascii=False), flush=True)
                procs.append(subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT))
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                rows = observe('parent_holds_real_assignment_row_lock')
                if len(rows) == 2 and all(row['wait_event_type'] == 'Lock' and row['blockers'] for row in rows):
                    assert any(holder_pid in row['blockers'] for row in rows)
                    assert all('FOR UPDATE' in row['query'] for row in rows)
                    break
                if any(proc.poll() is not None for proc in procs):
                    raise AssertionError('Worker exited before reaching lock; inspect its SQL log')
                time.sleep(0.025)
            else:
                raise AssertionError('Did not observe both real workers blocked on PostgreSQL locks')
        deadline = time.monotonic() + 35
        while any(proc.poll() is None for proc in procs) and time.monotonic() < deadline:
            observe('parent_released_workers_compete')
            time.sleep(0.025)
        for proc in procs:
            assert proc.wait(timeout=5) == 0
        results = [json.loads((EVIDENCE / f'r2-pg-{label}-result.json').read_text()) for label in labels]
        assert len({item['os_pid'] for item in results}) == 2
        assert len({item['pg_pid'] for item in results}) == 2
        print('RACE_RESULT', name, json.dumps(results, ensure_ascii=False), flush=True)
        return {'name': name, 'results': results, 'lock_snapshots': len(snapshots),
                'worker_blocks_worker': any(
                    row['blockers'] and any(pid in {r['pg_pid'] for r in results} for pid in row['blockers'])
                    for snap in snapshots if snap['phase'] == 'parent_released_workers_compete'
                    for row in snap['activity'])}
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
        for log in logs:
            log.close()
        json_write(EVIDENCE / f'r2-pg-{name}-locks.json',
                   {'sql': LOCK_SQL, 'lock_sql': LOCK_DETAIL_SQL, 'snapshots': snapshots})


def main():
    bootstrap()
    import psycopg2
    from django.db import connection, connections
    from practical_training.models import RepairClaim, ServerEvidence
    from practical_training.tests import TrainingTestCase, GOOD_POLICY
    from skill_review.models import SubmissionSnapshot, VerificationResult, DownstreamNotice, RetestAssignment
    from learning_map.models import VerificationFact

    class Handler(BaseHTTPRequestHandler):
        solved = False
        requests = 0
        challenge_key = None
        def do_GET(self):
            if self.path != '/api/Challenges':
                self.send_error(404)
                return
            type(self).requests += 1
            # Real network delay creates a reproducible worker-to-worker lock wait.
            if type(self).solved:
                time.sleep(0.8)
            body = json.dumps({'data': [{'key': type(self).challenge_key,
                                         'solved': type(self).solved}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, fmt, *args):
            print('HTTP_FIXTURE', fmt % args, flush=True)

    server = ThreadingHTTPServer(('127.0.0.1', 58165), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monitor = psycopg2.connect(os.environ['DATABASE_URL'], application_name='r2pg-monitor')
    monitor.autocommit = True
    report = {'database': 'module5_r2', 'mocked_locks': False,
              'challenge_source': 'local HTTP fixture, NOT live Juice Shop', 'races': []}
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT version(), current_database(), inet_server_addr(), inet_server_port(), '
                        'current_setting(\'transaction_isolation\'), current_setting(\'fsync\')')
            report['database_identity'] = cur.fetchone()
        # Call only setUp, not TestCase.setUpClass/_pre_setup: no enclosing test
        # transaction, so all fixture writes are committed and visible to children.
        fixture = TrainingTestCase(methodName='runTest')
        fixture.setUp()
        Handler.challenge_key = fixture.mapping.challenge_key
        assert Handler.challenge_key == 'directoryListingChallenge'
        report['challenge_key'] = Handler.challenge_key
        assignment = fixture.allocate()
        response = fixture.client.post(fixture.url(assignment, 'start/'), {}, format='json')
        assert response.status_code == 200, response.content
        assert Handler.requests == 1
        Handler.solved = True
        key = {'key': 'r2-pg-same-evidence'}
        first = race('challenge-same-key', fixture, assignment, 'verify/', [key, key], monitor)
        report['races'].append(first)
        assert sorted(row['status'] for row in first['results']) == [200, 201]
        assert len({row['body']['evidence_id'] for row in first['results']}) == 1
        assert first['worker_blocks_worker'], first
        assert Handler.requests == 2, 'Duplicate verifier network execution'
        assert ServerEvidence.objects.count() == SubmissionSnapshot.objects.count() == 1
        assert VerificationResult.objects.count() == VerificationFact.objects.count() == 1
        assert DownstreamNotice.objects.get().status == 'sent'
        assert RetestAssignment.objects.count() == 1
        report['after_challenge'] = {'evidence': 1, 'submission': 1, 'result': 1, 'fact': 1,
                                     'notice': 1, 'retest': 1, 'http_requests_including_baseline': Handler.requests}
        payload = {'key': 'r2-pg-same-claim', 'explanation': '服务端读取前验证身份、租户和资源权限。',
                   'policy': GOOD_POLICY}
        claim_race = race('repair-duplicate-submit', fixture, assignment, 'repair/', [payload, payload], monitor)
        report['races'].append(claim_race)
        assert sorted(row['status'] for row in claim_race['results']) == [200, 201]
        assert len({row['body']['claim_id'] for row in claim_race['results']}) == 1
        assert RepairClaim.objects.count() == 1
        claim = RepairClaim.objects.get()
        assert claim.evidence_id is None and claim.attempt.submissions.count() == 0
        changed = {**payload, 'explanation': '同键异内容必须拒绝。'}
        conflict = race('repair-key-content-conflict', fixture, assignment, 'repair/', [payload, changed], monitor)
        report['races'].append(conflict)
        assert sorted(row['status'] for row in conflict['results']) == [200, 400]
        verify_key = {'key': 'r2-pg-same-repair-evidence'}
        checked = race('repair-same-evidence', fixture, assignment,
                       f'repair/{claim.claim_id}/verify/', [verify_key, verify_key], monitor)
        report['races'].append(checked)
        assert sorted(row['status'] for row in checked['results']) == [200, 201]
        assert len({row['body']['evidence_id'] for row in checked['results']}) == 1
        claim.refresh_from_db()
        assert claim.completed and claim.retest.status == 'completed' and claim.retest.outcome == 'passed'
        # Fresh key on an already-submitted attempt must not add a submission.
        again = race('challenge-repeat-new-keys', fixture, assignment, 'verify/',
                     [{'key': 'r2-pg-repeat-a'}, {'key': 'r2-pg-repeat-b'}], monitor)
        report['races'].append(again)
        assert [row['status'] for row in again['results']] == [400, 400]
        counts = {'evidence': ServerEvidence.objects.count(), 'submission': SubmissionSnapshot.objects.count(),
                  'result': VerificationResult.objects.count(), 'fact': VerificationFact.objects.count(),
                  'notice': DownstreamNotice.objects.count(), 'repair_claim': RepairClaim.objects.count(),
                  'retest': RetestAssignment.objects.count(),
                  'first_effective': SubmissionSnapshot.objects.filter(first_effective=True).count(),
                  'notice_sent': DownstreamNotice.objects.filter(status='sent').count(),
                  'http_requests_including_baseline': Handler.requests}
        assert counts == {'evidence': 2, 'submission': 2, 'result': 2, 'fact': 2, 'notice': 2,
                          'repair_claim': 1, 'retest': 1, 'first_effective': 2, 'notice_sent': 2,
                          'http_requests_including_baseline': 2}, counts
        report.update(final_counts=counts, passed=True)
        print('FINAL_COUNTS', json.dumps(counts), flush=True)
    except Exception:
        report.update(passed=False, exception=traceback.format_exc())
        raise
    finally:
        json_write(EVIDENCE / 'r2-pg-concurrency-results.json', report)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        monitor.close()
        connections.close_all()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--label')
    parser.add_argument('--student', type=int)
    parser.add_argument('--url')
    parser.add_argument('--payload')
    args = parser.parse_args()
    if args.worker:
        worker(args)
    else:
        main()
