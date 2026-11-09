"""Only copied into isolated watchdog fixtures; never modifies the real report."""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--mode', choices=('normal', 'jsonl-error'), required=True)
    parser.add_argument('--duration', type=float, default=0.05)
    parser.add_argument('--finish-after', type=int, default=2)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not root.is_relative_to(Path('/home/hatch/workspace/ctf-data-security/.state')):
        raise SystemExit('FIXTURE_PATH_ESCAPE')
    if Path(__file__).resolve().parent != root or Path.cwd() != root:
        raise SystemExit('FIXTURE_WORKER_NOT_COPIED')
    record = root / 'session.jsonl'
    starts = sum(json.loads(line).get('type') == 'execution_started' for line in record.read_text().splitlines())
    with record.open('a') as output:
        output.write(json.dumps({'type': 'execution_started', 'session_id': args.resume, 'pid': os.getpid()}) + '\n')
    time.sleep(args.duration)
    if starts + 1 < args.finish_after:
        if args.mode == 'jsonl-error':
            with record.open('a') as output:
                output.write(json.dumps({'type': 'error', 'code': 'FIXTURE_SESSION_ONLY_EXCEPTION'}) + '\n')
        return 0
    candidate = 'a' * 40
    (root / 'report.md').write_text(
        f'## 第 1 期：隔离夹具\n### 候选 {candidate}\n候选状态：active\n第 1 期完成\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
