"""Check real day-3/day-7 eligibility without advancing time or awarding retention.

This command never reuses an old solved instance and never claims to have run a
learner's retest. A teacher must supply a fresh reviewed task and real new attempt.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--plan', required=True, type=Path)
parser.add_argument('--checkpoint', choices=('day3', 'day7'), required=True)
args = parser.parse_args()
plan = json.loads(args.plan.read_text())
item = next(row for row in plan['observations'] if row['checkpoint'] == args.checkpoint)
now = datetime.now(timezone.utc)
due = datetime.fromisoformat(item['due_at'])
result = {
    'checked_at': now.isoformat(), 'checkpoint': args.checkpoint, 'due_at': due.isoformat(),
    'plan_sha256': hashlib.sha256(args.plan.read_bytes()).hexdigest(),
    'baseline_evidence_id': plan['baseline']['evidence_id'],
    'baseline_attempt_id': plan['baseline']['attempt_id'],
    'status': 'time_elapsed_needs_real_learner_and_fresh_evidence' if now >= due else 'awaiting_real_time',
    'remaining_seconds': max(0, int((due - now).total_seconds())),
    'retention_proven': False,
    'next_steps': plan['requirements'],
    'automatic_scheduler_installed': False,
}
print(json.dumps(result, indent=2))
