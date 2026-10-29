"""Real release/HTTP/reader acceptance in an isolated DB, with no fabricated signoff.

Course and environment admission deliberately remain CLOSED. This operator-side
harness exercises the existing fixed observer and trusted evidence handoff, not
the gated production start/verify admission routes. Accounts are test identities.
"""
from datetime import timedelta
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
E = ROOT / 'evidence/module5'
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DATABASE_BACKEND'] = 'sqlite'
os.environ['SQLITE_DATABASE_PATH'] = sys.argv[1]
os.environ['DJANGO_SETTINGS_MODULE'] = 'ctf_backend.settings'
import django

django.setup()
from django.conf import settings
from django.utils import timezone
from challenges.models import Category, Challenge, ChallengeContainer
from learning_map.models import Capability, CatalogVersion, TaskAttempt, TaskPackage, VerificationFact
from practical_training.curriculum import HINTS, MATERIAL, REPAIR_MATERIAL
from practical_training.evidence import persist_evidence, request_digest, source_binding
from practical_training.lifecycle import reconcile_cleanup
from practical_training.models import ChallengeMapping, EnvironmentApproval, LabAssignment, ServerEvidence
from practical_training.policy import AUP_VERSION
from practical_training.services import CHALLENGE_VERIFIER, REPAIR_VERIFIER, audit, task_snapshot
from practical_training.verifiers import observe_challenge
from rest_framework.authtoken.models import Token
from skill_review.services.retest import schedule_retest
from users.models import CTFUser

for flag in ('LEARNING_MAP_AI_ENABLED', 'KNOWLEDGE_RAG_SEMANTIC_ENABLED',
             'AGENT_RUNTIME_SEMANTIC_RETRIEVAL', 'TUTOR_AGENT_ROUTER_ENABLED',
             'TUTOR_SPECIALISTS_ENABLED', 'TUTOR_CONTEXT_ENABLED', 'PRACTICAL_TRAINING_ENABLED'):
    setattr(settings, flag, False)

manifest = json.loads((E / 'r2-live-manifest.json').read_text())
assert Path(settings.DATABASES['default']['NAME']).resolve() == Path(sys.argv[1]).resolve()
assert not LabAssignment.objects.exists(), 'Use a fresh dedicated acceptance database'
wire = []
observations = []


def exchange(label, url, *, token=None, method='GET', payload=None):
    from urllib.parse import urlsplit
    target = urlsplit(url)
    assert target.hostname == '127.0.0.1', 'Local acceptance only'
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Token ' + token
    body = json.dumps(payload).encode() if payload is not None else None
    connection = http.client.HTTPConnection(target.hostname, target.port, timeout=15)
    try:
        connection.request(method, target.path or '/', body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        row = {'at': timezone.now().isoformat(), 'label': label,
               'request': {'method': method, 'url': url, 'payload': payload,
                           'authorization': 'REDACTED' if token else None},
               'response': {'status': response.status, 'headers': dict(response.getheaders()),
                            'body': data.decode('utf-8', errors='replace'),
                            'sha256': hashlib.sha256(data).hexdigest()}}
        wire.append(row)
        (E / f'r2-http-{len(wire):03d}-{label}.json').write_text(json.dumps(row, ensure_ascii=False, indent=2))
        return response.status, data
    finally:
        connection.close()


def unix_probe(instance):
    connection = http.client.HTTPConnection('localhost', timeout=10)
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.connect(instance['socket'])
    try:
        connection.request('GET', '/__r2__/probe')
        response = connection.getresponse()
        assert response.status == 200
        return json.loads(response.read())
    finally:
        connection.close()


def process_tree(pid):
    children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
    answer = [pid]
    for child in children:
        answer.extend(process_tree(int(child)))
    return answer


def observation(name, phase):
    instance = manifest['instances'][name]
    endpoint = f"http://127.0.0.1:{instance['observer_port']}"
    status, raw = exchange(f'{phase}-{name}-raw-state', endpoint + '/api/Challenges')
    assert status == 200
    matching = [r for r in json.loads(raw)['data'] if r['key'] == 'directoryListingChallenge']
    assert len(matching) == 1
    observed = observe_challenge(endpoint, 'directoryListingChallenge')
    assert observed['solved'] is matching[0]['solved']
    entry = {'student': name, 'phase': phase, 'endpoint': endpoint, 'at': timezone.now().isoformat(),
             'observer_version': CHALLENGE_VERIFIER, 'observation': observed,
             'paired_raw_response_sha256': hashlib.sha256(raw).hexdigest(),
             'note': 'Raw capture and unchanged fixed reader each performed an actual GET, with no solve between them.'}
    observations.append(entry)
    (E / 'r2-reader-observations.json').write_text(json.dumps(observations, indent=2))
    return observed


assert exchange('host-canary', 'http://127.0.0.1:18390/')[0] == 200
catalog = CatalogVersion.objects.create(version='m5-r2-local-20261029', label='R2 local acceptance, NOT teacher-approved', status='draft')
capability = Capability.objects.create(catalog=catalog, stable_id='M5-R2-LOCAL', track='network',
                                      title='Local document authorization acceptance',
                                      observable_objective='Observe actual server-side challenge state', dimension='operate', status='open')
challenge = Challenge.objects.create(title='Juice Shop 20.2.0 release acceptance (not Docker)',
    category=Category.objects.create(name='R2 local acceptance'), difficulty='easy', score=0,
    flag='', submission_mode='practice', docker_image=settings.JUICE_SHOP_IMAGE)
tasks = []
for key, purpose, version, material in (
    ('M5-R2-LIVE', 'verification', CHALLENGE_VERIFIER, MATERIAL),
    ('M5-R2-REPAIR', 'retest', REPAIR_VERIFIER, REPAIR_MATERIAL),
):
    task = TaskPackage.objects.create(catalog=catalog, task_key=key, version='1.0.0', title=key,
        track='network', purpose=purpose, execution_mode='isolated_challenge', status='draft',
        environment_available=False, challenge=challenge, materials=material, hints=HINTS,
        validator={'type': 'server_verifier', 'version': version},
        acceptance={'server_evidence': True, 'scope': material['scope']})
    task.capabilities.set([capability])
    tasks.append(task)
tasks[0].retest_task_keys = [tasks[1].task_key]
tasks[0].save(update_fields=['retest_task_keys'])
mapping = ChallengeMapping.objects.create(task=tasks[0], repair_task=tasks[1])
assignments, tokens = {}, {}
for name, instance in manifest['instances'].items():
    user = CTFUser.objects.create_user(username='r2-local-' + name, role='student')
    tokens[name] = Token.objects.create(user=user).key
    attempt = TaskAttempt.objects.create(student=user, task=tasks[0], catalog=catalog,
        task_version=tasks[0].version, capability_ids=[capability.stable_id], status='claimed')
    now = timezone.now()
    runtime_source = {'profile': 'r2-host-process', 'docker_used': False, 'release_version': '20.2.0',
                      'release_sha256': 'dbb457f74e908e28c41d7787e36d30d121d5b9f6178524720567b4aeb41f2968',
                      'supervisor_pid': instance['supervisor_pid'], 'app_port': instance['app_port'],
                      'observer_port': instance['observer_port'], 'student_port': instance['student_port']}
    container = ChallengeContainer.objects.create(user=user, challenge=challenge,
        container_id=f"r2-process-{instance['supervisor_pid']}", docker_container_name='', status='running',
        port=instance['student_port'], access_url=f"http://127.0.0.1:{instance['student_port']}/",
        started_at=now, expires_at=now + timedelta(hours=1), runtime_metadata=runtime_source)
    assignments[name] = LabAssignment.objects.create(mapping=mapping, attempt=attempt, container=container,
        expires_at=container.expires_at, task_snapshot=task_snapshot(tasks[0]),
        policy={'scope': 'local_acceptance_not_production_admission', 'memory_as_bytes': 2147483648,
                'cpu_affinity_cores': 1, 'pids_cap': None, 'outbound': 'private_loopback_only'},
        scope={'target': container.access_url, 'port': container.port, 'container_id': container.container_id,
               'verifier_endpoint': f"http://127.0.0.1:{instance['observer_port']}",
               'aup_version': AUP_VERSION, 'ends_at': container.expires_at.isoformat(),
               'acceptance_scope': 'operator-only local evidence path, not production start/verify'})

control = {'assignments': {name: str(a.assignment_id) for name, a in assignments.items()}}
Path(manifest['control']).write_text(json.dumps(control))
platform = manifest['platform'] + '/api/practical-training/assignments/'
for name, assignment in assignments.items():
    own = platform + str(assignment.assignment_id) + '/'
    status, body = exchange('before-baseline-' + name, own, token=tokens[name])
    assert status == 200 and json.loads(body)['scope']['target'] == ''
    assert exchange('admission-still-closed-' + name, own + 'start/', token=tokens[name], method='POST', payload={})[0] == 400
    assert observation(name, 'baseline')['solved'] is False
    # Operator acceptance path only: never assert missing course/environment approvals.
    assignment.baseline_observed_at = timezone.now()
    assignment.state = 'active'
    assignment.save(update_fields=['baseline_observed_at', 'state'])
    assignment.attempt.status = 'in_progress'
    assignment.attempt.save(update_fields=['status'])
    audit(assignment.attempt.student, 'r2_real_baseline', assignment,
          scope='isolated_operator_acceptance_not_production_admission')
    status, body = exchange('owner-address-' + name, own, token=tokens[name])
    assert status == 200 and json.loads(body)['scope']['target'] == assignment.container.access_url
    peer = 'student-b' if name == 'student-a' else 'student-a'
    assert exchange('cross-student-address-' + name, own, token=tokens[peer])[0] == 404
    assert exchange('anonymous-address-' + name, own)[0] in (401, 403)
    assert exchange('anonymous-gateway-' + name, assignment.container.access_url)[0] == 401
    assert exchange('cross-student-gateway-' + name, assignment.container.access_url, token=tokens[peer])[0] == 403
    probe = unix_probe(manifest['instances'][name])
    assert probe['node_running'] and not probe['host_path_visible']
    assert probe['connect_attempts']['own_loopback']['errno'] == 0
    assert all(result['errno'] != 0 for label, result in probe['connect_attempts'].items() if label != 'own_loopback')
    assert probe['memory_enforcement_probe']['stdout'].strip() == 'HOST_RLIMIT_AS_ENFORCED'
    host_processes = {}
    for pid in process_tree(manifest['instances'][name]['supervisor_pid']):
        status_text = Path(f'/proc/{pid}/status').read_text()
        cmdline = Path(f'/proc/{pid}/cmdline').read_bytes().decode().replace('\0', ' ')
        host_processes[str(pid)] = {'cmdline': cmdline, 'status': status_text,
                                    'limits': Path(f'/proc/{pid}/limits').read_text()}
        if '/app/build/app.js' in cmdline:
            assert 'CapEff:\t0000000000000000' in status_text
            assert 'NoNewPrivs:\t1' in status_text
            assert '2147483648' in host_processes[str(pid)]['limits']
    probe['host_processes'] = host_processes
    (E / f'r2-{name}-live-controls.json').write_text(json.dumps(probe, indent=2))

# Discover and retrieve the document through the actual student HTTP surface.
positive = assignments['student-b']
base = positive.container.access_url.rstrip('/')
assert exchange('student-b-home', base + '/', token=tokens['student-b'])[0] == 200
status, directory = exchange('student-b-document-directory', base + '/ftp', token=tokens['student-b'])
assert status == 200
links = re.findall(r'href=[\"\']([^\"\']+)[\"\']', directory.decode())
assert any('acquisitions.md' in link for link in links), 'Expected real directory discovery link'
status, document = exchange('student-b-document-read', base + '/ftp/acquisitions.md', token=tokens['student-b'])
assert status == 200 and document
assert observation('student-a', 'peer-solved-negative')['solved'] is False
assert observation('student-b', 'actual-document-solved')['solved'] is True

results = {}
for name, assignment in assignments.items():
    observed = observation(name, 'handoff')
    source = source_binding(assignment, assignment.attempt, 'r2_real_juice_release')
    source.update({'baseline_observed_at': assignment.baseline_observed_at.isoformat(),
                   'runtime': assignment.container.runtime_metadata,
                   'observer_endpoint': assignment.scope['verifier_endpoint'],
                   'scope': 'local_operator_acceptance_no_production_admission'})
    row = persist_evidence(assignment=assignment, attempt=assignment.attempt, key='r2-real-' + name,
        request_hash=request_digest(assignment, assignment.attempt, 'r2-real-juice'), source=source,
        observation=observed, version=CHALLENGE_VERIFIER, status='passed' if observed['solved'] else 'failed')
    row.result.refresh_from_db()
    assert row.result.module1_fact_ids
    assert row.result.attempt_id == assignment.attempt_id
    assert row.result.overall_status == ('passed' if name == 'student-b' else 'failed')
    results[name] = {'assignment_id': str(assignment.assignment_id), 'attempt_id': str(assignment.attempt.attempt_id),
        'student_id': assignment.attempt.student_id, 'evidence_id': str(row.evidence_id),
        'result_id': str(row.result.result_id), 'module1_fact_ids': row.result.module1_fact_ids,
        'status': row.status, 'source': source, 'observed_at': row.observed_at.isoformat()}
    if name == 'student-b':
        retest, _ = schedule_retest(row.result.submission, now=row.observed_at, due_days=3)
        plan = {'baseline': results[name], 'database': str(Path(sys.argv[1]).resolve()),
            'account_kind': 'operator-driven synthetic student; not human retention evidence',
            'course_signoff': 'pending_human', 'module6_retest_id': str(retest.assignment_id),
            'module6_retest_status': retest.status,
            'requirements': ['genuine wall time elapsed', 'teacher-signed fresh task/environment',
                             'fresh unsolved instance', 'same learner identity', 'new attempt linked to original',
                             'server evidence, no old solved-state replay'],
            'observations': [{'checkpoint': f'day{days}', 'due_at': (row.observed_at + timedelta(days=days)).isoformat(),
                              'status': 'awaiting_real_time_and_learner', 'observed_at': None} for days in (3, 7)]}
        (E / 'r2-delayed-retest-plan.json').write_text(json.dumps(plan, indent=2))
assert EnvironmentApproval.objects.count() == 0 and mapping.reviewed_by_id is None
assert ServerEvidence.objects.count() == 2
(E / 'r2-real-handoff.json').write_text(json.dumps(results, indent=2))
print('REAL_CHALLENGE_AND_ATTRIBUTION_PASSED', flush=True)

# Shorten this disposable authorization, then wait for real time and real cleanup.
expiry = timezone.now() + timedelta(seconds=12)
for assignment in assignments.values():
    assignment.expires_at = expiry
    assignment.scope['ends_at'] = expiry.isoformat()
    assignment.save(update_fields=['expires_at', 'scope'])
    audit(None, 'r2_expiry_scheduled', assignment, expires_at=expiry.isoformat())
control['expire_at'] = expiry.timestamp()
Path(manifest['control']).write_text(json.dumps(control))
while timezone.now() < expiry + timedelta(seconds=3):
    time.sleep(0.25)
for name, assignment in assignments.items():
    own = platform + str(assignment.assignment_id) + '/'
    status, body = exchange('expired-platform-' + name, own, token=tokens[name])
    assert status == 200 and json.loads(body)['state'] == 'expired'
    assert json.loads(body)['scope']['target'] == ''
    Token.objects.filter(user=assignment.attempt.student).delete()
    assert exchange('revoked-credential-' + name, own, token=tokens[name])[0] in (401, 403)
for _ in range(80):
    if (E / 'r2-runtime-cleanup.json').exists():
        break
    time.sleep(0.25)
receipt = json.loads((E / 'r2-runtime-cleanup.json').read_text())
for name, assignment in assignments.items():
    assert receipt['instances'][name]['supervisor_gone']
    assert all(value != 0 for value in receipt['instances'][name]['ports_errno'].values())
    for pid in json.loads((E / f'r2-{name}-live-controls.json').read_text())['host_processes']:
        assert not Path('/proc/' + pid).exists(), 'Captured instance process still exists'
    container = assignment.container
    container.status = 'destroyed'
    container.destroyed_at = timezone.now()
    container.access_url = ''
    container.save(update_fields=['status', 'destroyed_at', 'access_url'])
assert reconcile_cleanup() == 2
for assignment in assignments.values():
    assignment.refresh_from_db()
    assert assignment.physical_cleanup == 'confirmed_by_runtime'
summary = {'finished_at': timezone.now().isoformat(), 'real_juice_version': '20.2.0',
           'positive_student': 'student-b', 'negative_student': 'student-a',
           'production_admission': 'CLOSED, no signoff/approval fabricated', 'wire_exchanges': len(wire),
           'server_evidence_count': ServerEvidence.objects.count(), 'fact_count': VerificationFact.objects.count(),
           'real_cleanup': receipt, 'remaining': ['cgroup CPU bandwidth/RSS/PID caps unavailable',
             'trusted host root and internal observer ports are outside the student process boundary',
             'local HTTP harness is not a deployed multi-host production gateway',
             'teacher signoff and genuine day3/day7 learner observation pending']}
(E / 'r2-live-summary.json').write_text(json.dumps(summary, indent=2))
print('REAL_EXPIRY_PORTS_AND_CREDENTIALS_PASSED', flush=True)
