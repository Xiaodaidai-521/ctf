"""Local single-session supervision. Never writes an execution completion marker."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import UUID

WORKDIR = Path('/home/hatch/workspace/ctf-data-security')
RECORDS = Path('/home/hatch/workspace/data-security-seven-phases')
CLI = Path('/home/hatch/.local/bin/claude')
MAX_OBSERVATION_BYTES = 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def report_state(text, phase, candidate):
    """Only one active candidate, inside one phase, can finish or be accepted."""
    if not re.fullmatch(r'[0-9a-f]{40}', candidate or ''):
        return False, False
    section = False
    phase_count = 0
    fence = None
    comment = False
    blocks = []
    block = None
    for line in text.splitlines():
        if '<!--' in line:
            comment = '-->' not in line.split('<!--', 1)[1]
            continue
        if comment:
            comment = '-->' not in line
            continue
        stripped = line.lstrip()
        match = re.match(r'^(`{3,}|~{3,})', stripped)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        if line.startswith('## '):
            section = line.startswith(f'## 第 {phase} 期：')
            phase_count += int(section)
            block = None
        elif line.startswith('### '):
            block = None
            if section and re.fullmatch(r'### 候选 [0-9a-f]{40}', line):
                block = (line.removeprefix('### 候选 '), [])
                blocks.append(block)
        elif block is not None:
            block[1].append(line)
    targets = [lines for sha, lines in blocks if sha == candidate]
    active = [sha for sha, lines in blocks if '候选状态：active' in lines]
    if phase_count != 1 or len(targets) != 1 or active != [candidate]:
        return False, False
    lines = targets[0]
    complete = (lines.count('候选状态：active') == 1 and
                lines.count(f'第 {phase} 期完成') == 1 and '候选状态：invalidated' not in lines)
    accepted = (complete and lines.count('验收结论：亲验通过') == 1 and
                lines.count(f'亲验 SHA：{candidate}') == 1)
    return complete, accepted


def process(pid):
    try:
        root = Path('/proc') / str(pid)
        stat = (root / 'stat').read_text().rsplit(') ', 1)[1].split()
        if stat[0] == 'Z':
            return None
        args = (root / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')
        return {'pid': int(pid), 'start_ticks': int(stat[19]),
                'cwd': os.readlink(root / 'cwd'), 'argv': args}
    except (OSError, UnicodeError, ValueError, IndexError):
        return None


def session_processes(config):
    found = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        item = process(path.name)
        if item is None or item['cwd'] != config['workdir']:
            continue
        args = item['argv']
        if config.get('fixture'):
            if config['worker'] not in args:
                continue
        elif not args or Path(args[0]).name not in ('claude', 'claude.exe'):
            continue
        # The initial SDK launch may allocate its ID after process creation. Pin
        # that one process in full; all subsequent launches must use --resume.
        initial = config.get('initial_process')
        if (not config.get('fixture') and initial == item and
                '--session-id' not in args and '--resume' not in args):
            found.append(item)
            continue
        for flag in ('--session-id', '--resume'):
            if args.count(flag) == 1 and args.index(flag) + 1 < len(args):
                if args[args.index(flag) + 1] == config['session_id']:
                    found.append(item)
                    break
    return found


def operator_block(value):
    if type(value) is not dict:
        return False
    if value.get('type') in ('user_cancelled', 'permission_denied', 'authorization_required'):
        return True
    if value.get('permissionDecision') == 'deny':
        return True
    # API request snapshots can replay old tool results; they are not new controls.
    if value.get('type') not in ('user', 'tool', 'tool_result'):
        return False
    message = value.get('message')
    if type(message) is not dict:
        return False
    content = message.get('content')
    if content in ('[Request interrupted by user]', '[Request interrupted by user for tool use]'):
        return True
    if type(content) is not list:
        return False
    for part in content:
        if type(part) is not dict or part.get('type') != 'tool_result' or not part.get('is_error'):
            continue
        body = part.get('content')
        if type(body) is list:
            body = ' '.join(p.get('text', '') for p in body if type(p) is dict and type(p.get('text')) is str)
        if type(body) is str:
            if re.search(r'user (?:denied|declined)|request interrupted by user|tool use (?:rejected|denied)', body, re.I):
                return True
            # An OS EACCES failure is a task error, not the user's permission decision.
            if not re.search(r'PermissionError|Errno 13|EACCES', body) and re.search(
                r'^\s*(?:error:\s*)?permission(?: to [^\n]{1,100})? (?:was )?denied(?:[.:]|\s*$)',
                body, re.I | re.M,
            ):
                return True
    return False


def observation(path, previous=None):
    """Incremental bounded reading; only hashes/offsets and control states escape."""
    target = Path(path)
    previous = previous or {}
    try:
        stat = target.stat()
        offset = previous.get('scan_offset', 0)
        if previous.get('inode') != stat.st_ino or offset > stat.st_size:
            offset = 0
        blocked = False
        consumed = 0
        partial = False
        window = hashlib.sha256()
        with target.open('rb') as stream:
            stream.seek(offset)
            while consumed < MAX_OBSERVATION_BYTES:
                line = stream.readline(MAX_OBSERVATION_BYTES + 1)
                if not line:
                    break
                if len(line) > MAX_OBSERVATION_BYTES:
                    blocked = True
                    break
                if target.suffix == '.jsonl' and not line.endswith(b'\n'):
                    partial = True
                    break
                consumed += len(line)
                offset += len(line)
                window.update(line)
                try:
                    blocked = operator_block(json.loads(line)) or blocked
                except (ValueError, UnicodeError):
                    continue
        return {'exists': True, 'inode': stat.st_ino, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                'scan_offset': offset, 'window_sha256': window.hexdigest(), 'blocked': blocked,
                'pending': partial or offset < stat.st_size}
    except OSError:
        return {'exists': False, 'blocked': False, 'pending': False}


def save(path, value):
    target = Path(path)
    temporary = target.with_name(target.name + '.new')
    with temporary.open('w', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(target)


def log(config, event, **fields):
    with Path(config['watchdog_log']).open('a', encoding='utf-8') as stream:
        os.chmod(config['watchdog_log'], 0o600)
        stream.write(json.dumps({'time': now(), 'event': event,
                                 'session_id': config['session_id'], **fields}, ensure_ascii=False) + '\n')


def validate(config, fixture_root=None):
    if type(config.get('phase')) is not int or not 1 <= config['phase'] <= 7:
        raise ValueError('INVALID_PHASE')
    try:
        if str(UUID(config['session_id'])) != config['session_id']:
            raise ValueError('INVALID_SESSION')
    except (KeyError, TypeError, ValueError):
        raise ValueError('INVALID_SESSION') from None
    args = config['resume_argv']
    if type(args) is not list or not all(type(arg) is str for arg in args) or len(args) < 3:
        raise ValueError('INVALID_RESUME_COMMAND')
    if args.count('--resume') != 1 or args.index('--resume') + 1 >= len(args):
        raise ValueError('RESUME_MUST_KEEP_SESSION')
    if args[args.index('--resume') + 1] != config['session_id'] or '--session-id' in args:
        raise ValueError('RESUME_MUST_KEEP_SESSION')
    if config.get('operator_state', 'active') not in ('active', 'paused', 'blocked', 'cancelled'):
        raise ValueError('INVALID_OPERATOR_STATE')
    if fixture_root is not None:
        root = Path(fixture_root).resolve()
        if not root.is_relative_to(WORKDIR / '.state') or not config.get('fixture'):
            raise ValueError('FIXTURE_OUTSIDE_ISOLATION')
        for name in ('report', 'run_log', 'session_record', 'watchdog_log', 'workdir', 'worker'):
            if not Path(config[name]).resolve().is_relative_to(root):
                raise ValueError('FIXTURE_PATH_ESCAPE')
        if args[0] != sys.executable or args[1] != config['worker']:
            raise ValueError('INVALID_FIXTURE_WORKER')
    else:
        if config.get('fixture') or Path(config['workdir']).resolve() != WORKDIR:
            raise ValueError('INVALID_WORKDIR')
        if args[0] != str(CLI):
            raise ValueError('UNTRUSTED_EXECUTABLE')
        expected_paths = {'report': RECORDS / '实施报告.md',
            'run_log': RECORDS / f'logs/phase-{config["phase"]:02d}.log',
            'watchdog_log': RECORDS / f'logs/watchdog-phase-{config["phase"]:02d}.log',
            'session_record': Path('/home/hatch/.claude/projects/-home-hatch-workspace-ctf-data-security') /
                              (config['session_id'] + '.jsonl')}
        for name, expected in expected_paths.items():
            if Path(config[name]).resolve() != expected:
                raise ValueError('INVALID_RECORD_PATH')
        if config.get('authorization') != 'inherited-launch-no-escalation':
            raise ValueError('RESUME_AUTHORIZATION_REQUIRED')


def candidate_state(config, fixture_root=None):
    try:
        text = Path(config['report']).read_text(encoding='utf-8')
    except FileNotFoundError:
        text = ''
    complete, accepted = report_state(text, config['phase'], config.get('candidate_sha'))
    if complete and not fixture_root:
        for command, expected in (
            (['git', 'rev-parse', 'HEAD'], config['candidate_sha']),
            (['git', 'branch', '--show-current'], 'feat/data-security'),
            (['git', 'status', '--porcelain', '--untracked-files=all'], ''),
        ):
            result = subprocess.run(command, cwd=config['workdir'], capture_output=True, text=True,
                                    env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'), check=False)
            if result.returncode or result.stdout.strip() != expected:
                complete = accepted = False
                break
    return complete, accepted


def load(mapping):
    config = json.loads(mapping.read_text(encoding='utf-8'))
    control = mapping.with_suffix('.control.json')
    if control.exists():
        encoded = control.read_bytes()
        control_hash = hashlib.sha256(encoded).hexdigest()
        value = json.loads(encoded)
        if type(value) is not dict or set(value) - {'operator_state', 'candidate_sha', 'reason'}:
            raise ValueError('INVALID_OPERATOR_CONTROL')
        if config.get('control_sha256') != control_hash:
            for name in ('operator_state', 'candidate_sha'):
                if name in value:
                    config[name] = value[name]
            config['control_sha256'] = control_hash
    return config


def tick(config, mapping_path, *, fixture_root=None):
    validate(config, fixture_root)
    previous = config.get('last_observation', {})
    observations = {key: observation(config[key], previous.get(key)) for key in ('run_log', 'session_record')}
    config['last_observation'] = observations
    config['watchdog_pid'] = os.getpid()
    config['watchdog_start_ticks'] = process(os.getpid())['start_ticks']
    config['checked_at'] = now()
    changed = any(observations[key].get('size') != previous.get(key, {}).get('size') or
                  observations[key].get('mtime_ns') != previous.get(key, {}).get('mtime_ns')
                  for key in observations)
    if changed or 'last_progress_at' not in config:
        config['last_progress_at'] = now()
    if any(item['blocked'] for item in observations.values()):
        config['operator_state'] = 'blocked'
    if config.get('operator_state') != 'active':
        config['supervision_state'] = 'blocked'
        save(mapping_path, config)
        log(config, 'operator-or-permission-block')
        return 'blocked'
    complete, accepted = candidate_state(config, fixture_root)
    if complete and not any(item['pending'] for item in observations.values()):
        config['supervision_state'] = 'acceptance-passed' if accepted else 'awaiting-acceptance'
        save(mapping_path, config)
        log(config, 'valid-marker-stop-resume', accepted=accepted)
        return 'complete'
    if not observations['session_record']['exists']:
        config['supervision_state'] = 'blocked'
        save(mapping_path, config)
        log(config, 'missing-real-session-record')
        return 'blocked'
    running = session_processes(config)
    if len(running) > 1:
        config['operator_state'] = config['supervision_state'] = 'blocked'
        save(mapping_path, config)
        log(config, 'duplicate-execution-blocked', pids=[p['pid'] for p in running])
        return 'blocked'
    if running:
        config['pid'] = running[0]['pid']
        config['pid_start_ticks'] = running[0]['start_ticks']
        stalled = (datetime.now(timezone.utc) - datetime.fromisoformat(config['last_progress_at'])).total_seconds() > 900
        config['supervision_state'] = 'stalled' if stalled else 'running'
        save(mapping_path, config)
        log(config, 'stalled-needs-inspection' if stalled else 'heartbeat', pid=config['pid'],
            start_ticks=config['pid_start_ticks'], observations=observations)
        return 'running'
    if any(item['pending'] for item in observations.values()):
        config['supervision_state'] = 'observing'
        save(mapping_path, config)
        log(config, 'finish-reading-before-resume')
        return 'observing'
    # The main loop holds a singleton lock over observation, second check and spawn.
    if session_processes(config):
        return 'running'
    with Path(config['run_log']).open('ab') as output:
        child = subprocess.Popen(config['resume_argv'], cwd=config['workdir'], stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    identity = process(child.pid)
    config['pid'] = child.pid
    config['pid_start_ticks'] = identity['start_ticks'] if identity else None
    config['supervision_state'] = 'resuming'
    config.setdefault('resumes', []).append({'at': now(), 'pid': child.pid,
        'start_ticks': config['pid_start_ticks'], 'session_id': config['session_id'],
        'reason': 'process-absent-marker-absent', 'observations': observations})
    save(mapping_path, config)
    log(config, 'resume-same-session', pid=child.pid)
    return 'resumed'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mapping', required=True)
    parser.add_argument('--interval', type=float, default=30)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--fixture-root')
    parser.add_argument('--next-phase', action='store_true')
    args = parser.parse_args()
    mapping = Path(args.mapping).resolve()
    if not args.fixture_root and mapping.parent != RECORDS / 'sessions':
        parser.error('mapping must be in the approved sessions directory')
    if args.fixture_root and not mapping.is_relative_to(Path(args.fixture_root).resolve()):
        parser.error('mapping must be inside fixture root')
    if args.interval < (0.02 if args.fixture_root else 30):
        parser.error('interval too short')
    if args.next_phase:
        config = load(mapping)
        validate(config, args.fixture_root)
        complete, accepted = candidate_state(config, args.fixture_root)
        observations = [observation(config[key], config.get('last_observation', {}).get(key))
                        for key in ('run_log', 'session_record')]
        allowed = (complete and accepted and config.get('operator_state') == 'active' and
                   all(item['exists'] and not item['blocked'] and not item['pending'] for item in observations))
        print(json.dumps({'complete': complete, 'accepted': accepted, 'next_phase_allowed': allowed}))
        return 0 if allowed else 1
    with mapping.with_suffix('.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 73
        while True:
            config = load(mapping)
            state = tick(config, mapping, fixture_root=args.fixture_root)
            if args.once or state == 'complete':
                return 0 if state != 'blocked' else 2
            time.sleep(args.interval)


if __name__ == '__main__':
    raise SystemExit(main())
