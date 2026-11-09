import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from tools.data_security import watchdog as w

ROOT = Path(__file__).resolve().parents[3]
SHA = 'a' * 40
GOOD = f'## 第 1 期：隔离夹具\n### 候选 {SHA}\n候选状态：active\n第 1 期完成\n'
ACCEPTED = GOOD + f'验收结论：亲验通过\n亲验 SHA：{SHA}\n'


class MarkerTests(unittest.TestCase):
    def test_completion_and_independent_acceptance_are_different(self):
        self.assertEqual(w.report_state(GOOD, 1, SHA), (True, False))
        self.assertEqual(w.report_state(ACCEPTED, 1, SHA), (True, True))

    def test_quoted_fenced_indented_template_other_phase_and_old_markers_do_not_complete(self):
        fixtures = (
            '```\n' + GOOD + '```\n', '~~~\n' + GOOD + '~~~\n',
            '\n'.join('> ' + line for line in GOOD.splitlines()),
            '\n'.join('    ' + line for line in GOOD.splitlines()),
            '<!--\n' + GOOD + '-->\n', GOOD.replace('第 1 期：', '第 2 期：'),
            GOOD.replace('候选状态：active', '候选状态：invalidated'),
            GOOD.replace(SHA, 'b' * 40), GOOD.replace('第 1 期完成', '`第 1 期完成`'),
            GOOD + '候选状态：invalidated\n', GOOD + GOOD,
            GOOD + '\n### 候选 ' + 'b' * 40 + '\n候选状态：active\n',
        )
        for number, text in enumerate(fixtures):
            with self.subTest(fixture=number):
                self.assertEqual(w.report_state(text, 1, SHA), (False, False))
        self.assertEqual(w.report_state(GOOD, 1, None), (False, False))

    def test_wrong_acceptance_sha_does_not_authorize_next_phase(self):
        text = ACCEPTED.replace('亲验 SHA：' + SHA, '亲验 SHA：' + 'b' * 40)
        self.assertEqual(w.report_state(text, 1, SHA), (True, False))

    def test_actual_candidate_gate_checks_head_branch_and_dirty_files(self):
        config = {'report': str(ROOT / '.state/does-not-exist'), 'candidate_sha': SHA, 'phase': 1,
                  'workdir': str(ROOT)}
        with patch.object(Path, 'read_text', return_value=ACCEPTED):
            for outputs in ([SHA, 'feat/data-security', ''], ['b' * 40], [SHA, 'main'],
                            [SHA, 'feat/data-security', ' M changed.py']):
                completed = [subprocess.CompletedProcess([], 0, stdout=value) for value in outputs]
                with patch.object(w.subprocess, 'run', side_effect=completed):
                    complete, accepted = w.candidate_state(config)
                    self.assertEqual((complete, accepted), (outputs == [SHA, 'feat/data-security', ''],) * 2)


class WatchdogFixtureTests(unittest.TestCase):
    def setUp(self):
        state = ROOT / '.state'
        state.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='watchdog-fixture-', dir=state))
        self.addCleanup(shutil.rmtree, self.root)
        self.mapping = self.root / 'mapping.json'
        worker = self.root / 'worker.py'
        shutil.copyfile(ROOT / 'tools/data_security/fixture_worker.py', worker)
        for filename in ('report.md', 'run.log', 'session.jsonl', 'watchdog.log'):
            (self.root / filename).write_text('')
        self.config = {'phase': 1, 'session_id': str(uuid4()), 'fixture': True,
            'workdir': str(self.root), 'worker': str(worker), 'report': str(self.root / 'report.md'),
            'run_log': str(self.root / 'run.log'), 'session_record': str(self.root / 'session.jsonl'),
            'watchdog_log': str(self.root / 'watchdog.log'), 'candidate_sha': SHA, 'operator_state': 'active',
            'resume_argv': [sys.executable, str(worker), '--resume', '', '--root', str(self.root), '--mode', 'normal']}
        self.config['resume_argv'][3] = self.config['session_id']
        w.save(self.mapping, self.config)
        self.children = []
        self.addCleanup(self.cleanup_children)

    def cleanup_children(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=10)
        # Resumed fixture workers are not children of the test runner.
        for item in w.session_processes(self.config):
            current = w.process(item['pid'])
            if current and current['start_ticks'] == item['start_ticks']:
                os.kill(item['pid'], 15)

    def launch_watchdog(self, *extra):
        args = [sys.executable, '-B', str(ROOT / 'tools/data_security/watchdog.py'),
                '--mapping', str(self.mapping), '--fixture-root', str(self.root), '--interval', '0.03', *extra]
        child = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.children.append(child)
        return child

    def starts(self):
        return [json.loads(line) for line in Path(self.config['session_record']).read_text().splitlines()
                if json.loads(line).get('type') == 'execution_started']

    def exercise_recovery(self, mode):
        self.config['resume_argv'][-1] = mode
        w.save(self.mapping, self.config)
        with Path(self.config['run_log']).open('ab') as log:
            first = subprocess.Popen(self.config['resume_argv'], cwd=self.root, stdout=log, stderr=log)
            self.children.append(first)
            self.assertEqual(first.wait(timeout=10), 0)
        self.assertEqual(Path(self.config['run_log']).read_bytes(), b'')
        self.assertEqual(Path(self.config['report']).read_text(), '')
        watchers = [self.launch_watchdog(), self.launch_watchdog()]
        exits = sorted(child.wait(timeout=15) for child in watchers)
        self.assertTrue(all(code in (0, 73) for code in exits))
        self.assertIn(0, exits)
        starts = self.starts()
        self.assertEqual(len(starts), 2)
        self.assertEqual({entry['session_id'] for entry in starts}, {self.config['session_id']})
        saved = json.loads(self.mapping.read_text())
        self.assertEqual(saved['supervision_state'], 'awaiting-acceptance')
        self.assertEqual(len(saved['resumes']), 1)
        self.assertEqual(self.launch_watchdog('--next-phase').wait(timeout=10), 1)
        Path(self.config['report']).write_text(ACCEPTED)
        self.assertEqual(self.launch_watchdog('--next-phase').wait(timeout=10), 0)
        if mode == 'jsonl-error':
            self.assertIn('FIXTURE_SESSION_ONLY_EXCEPTION', Path(self.config['session_record']).read_text())
        # Evidence callers report only aggregate assertions, never fixture report text.

    def test_normal_zero_exit_without_marker_resumes_same_session_once(self):
        self.exercise_recovery('normal')

    def test_exception_only_in_real_session_record_resumes_same_session_once(self):
        self.exercise_recovery('jsonl-error')

    def test_existing_process_and_pid_reuse_metadata_cannot_duplicate_execution(self):
        args = self.config['resume_argv'] + ['--duration', '2']
        with Path(self.config['run_log']).open('ab') as log:
            child = subprocess.Popen(args, cwd=self.root, stdout=log, stderr=log)
        self.children.append(child)
        deadline = time.monotonic() + 3
        while not w.session_processes(self.config) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.config.update(pid=child.pid, pid_start_ticks=-1)
        self.assertEqual(w.tick(self.config, self.mapping, fixture_root=self.root), 'running')
        self.assertEqual(self.config['pid'], child.pid)
        self.assertEqual(self.config['pid_start_ticks'], w.process(child.pid)['start_ticks'])
        self.assertFalse(self.config.get('resumes'))

    def test_permission_denial_is_sticky_and_never_autoresumes(self):
        record = Path(self.config['session_record'])
        record.write_text(json.dumps({'type': 'user', 'message': {'content': [
            {'type': 'tool_result', 'is_error': True, 'content': 'User denied this operation'}]}}) + '\n')
        self.assertEqual(w.tick(self.config, self.mapping, fixture_root=self.root), 'blocked')
        self.assertEqual(w.tick(w.load(self.mapping), self.mapping, fixture_root=self.root), 'blocked')
        self.assertFalse(self.starts())

    def test_os_access_errors_and_replayed_requests_are_not_user_denials(self):
        def event(body, kind='user'):
            return {'type': kind, 'message': {'content': [
                {'type': 'tool_result', 'is_error': True, 'content': body}]}}
        self.assertFalse(w.operator_block(event('PermissionError: [Errno 13] Permission denied')))
        self.assertFalse(w.operator_block(event('User denied this operation', 'api-request-blob')))
        for body in ('User denied this operation', 'User declined this operation',
                     'Permission to use Bash was denied.', 'Permission denied',
                     'Tool use rejected', 'PermissionError EACCES; user denied this operation'):
            self.assertTrue(w.operator_block(event(body)))

    def test_old_control_cannot_clear_a_later_permission_denial(self):
        w.save(self.mapping.with_suffix('.control.json'), {'operator_state': 'active', 'reason': 'fixture authorization'})
        config = w.load(self.mapping)
        Path(config['session_record']).write_text('{"type":"permission_denied"}\n')
        self.assertEqual(w.tick(config, self.mapping, fixture_root=self.root), 'blocked')
        self.assertEqual(w.load(self.mapping)['operator_state'], 'blocked')

    def test_paused_cancelled_missing_record_and_wrong_session_block(self):
        for state in ('paused', 'blocked', 'cancelled'):
            config = dict(self.config, operator_state=state)
            self.assertEqual(w.tick(config, self.mapping, fixture_root=self.root), 'blocked')
        Path(self.config['session_record']).unlink()
        self.assertEqual(w.tick(self.config, self.mapping, fixture_root=self.root), 'blocked')
        config = dict(self.config, session_id=str(uuid4()))
        with self.assertRaises(ValueError):
            w.validate(config, self.root)
        self.assertFalse(self.config.get('resumes'))

    def test_watchdog_stays_alive_while_operator_blocked(self):
        self.config['operator_state'] = 'blocked'
        w.save(self.mapping, self.config)
        child = self.launch_watchdog()
        deadline = time.monotonic() + 3
        while not Path(self.config['watchdog_log']).stat().st_size and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNone(child.poll())
        self.assertFalse(self.starts())

    def test_incremental_observation_does_not_lose_denial_behind_large_logs(self):
        record = Path(self.config['session_record'])
        filler = (json.dumps({'type': 'progress', 'count': 1}) + '\n').encode()
        record.write_bytes(filler * (w.MAX_OBSERVATION_BYTES // len(filler) + 100) + b'{"type":"permission_denied"}\n')
        first = w.observation(record)
        self.assertTrue(first['pending'])
        second = w.observation(record, first)
        self.assertTrue(second['blocked'])
        self.assertFalse(second['pending'])
        self.assertNotIn('permission_denied', json.dumps(second))

    def test_partial_session_record_never_triggers_resume(self):
        Path(self.config['session_record']).write_bytes(b'{"type":')
        self.assertEqual(w.tick(self.config, self.mapping, fixture_root=self.root), 'observing')
        self.assertFalse(self.config.get('resumes'))
