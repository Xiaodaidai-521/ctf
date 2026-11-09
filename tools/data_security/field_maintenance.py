"""Offline field maintenance, restricted to the existing isolated synthetic cluster."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

from tools.data_security import isolation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('inventory', 'prepare', 'backfill', 'finish', 'rotate', 'rotation-finish'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--recovery', type=Path)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--retry-failed', action='store_true')
    args = parser.parse_args()
    if Path.cwd() != isolation.ROOT or not re.fullmatch(r'phase4_fields_(src|dst)_[0-9a-f]{12}', args.database):
        parser.error('a dedicated phase-four synthetic database in the isolated worktree is required')
    if args.operation in ('prepare', 'backfill', 'finish') and not args.checkpoint:
        parser.error('--checkpoint is required')
    if args.operation == 'prepare' and not args.recovery:
        parser.error('--recovery is required')
    env = isolation.environment()
    env.update(DJANGO_SETTINGS_MODULE='ctf_backend.settings', DATA_SECURITY_CONFIG=str(args.config),
               DATABASE_BACKEND='postgres', DATABASE_URL='', DB_NAME=args.database,
               DB_HOST='127.0.0.1', DB_TRANSPORT='local', DB_SSLMODE='disable')
    os.environ.update(env)
    sys.path.insert(0, str(isolation.ROOT / 'backend'))
    import django
    django.setup()
    from django.db import DatabaseError
    from ctf_backend.security_bootstrap import assemble_field_backfill, assemble_field_rotation
    from data_security.contracts import ContractViolation

    try:
        if args.operation in ('rotate', 'rotation-finish'):
            maintenance = assemble_field_rotation(config_path=args.config)
            result = maintenance.run(limit=args.limit) if args.operation == 'rotate' else maintenance.finish()
        else:
            maintenance = assemble_field_backfill(config_path=args.config)
            if args.operation == 'inventory':
                result = maintenance.inventory()
            elif args.operation == 'prepare':
                result = maintenance.prepare(checkpoint=args.checkpoint,
                                             recovery=json.loads(args.recovery.read_bytes()))
            elif args.operation == 'backfill':
                result = maintenance.run(checkpoint=args.checkpoint, limit=args.limit, retry_failed=args.retry_failed)
            else:
                result = maintenance.finish(checkpoint=args.checkpoint)
    except (ContractViolation, RuntimeError, DatabaseError, ValueError, OSError):
        # CLI errors must not serialize SQL, field values, or filesystem/key material.
        print(json.dumps({'error': 'FIELD_MAINTENANCE_REFUSED'}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return int(bool(result.get('stopped') or result.get('failed') or result.get('conflicts')))


if __name__ == '__main__':
    raise SystemExit(main())
