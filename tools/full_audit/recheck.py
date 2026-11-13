"""Fresh complete remaining-platform run on the verified synthetic cluster.

Business-module regressions and independent-service checks run separately.
Pre-creating an empty WAL_LOG database avoids template-copy checkpoints without
changing fsync, authentication, assertions, or application configuration.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.full_audit.batch import execute, sources
from tools.full_audit.run import config_and_identity

TARGETS = ['data_security', 'resources', 'audit', 'agent_memory', 'agent_runtime',
           'agents', 'ai_assistant', 'announcements', 'articles', 'ctf_backend',
           'export_quota', 'export_risk', 'learning_analytics', 'learning_knowledge',
           'learning_map', 'legal', 'legal_kb', 'practical_training', 'rag_ingestion',
           'scripts', 'student_profiles', 'submissions', 'test_auth', 'teaching_agent']


def main():
    import psycopg2
    from psycopg2 import sql
    config = config_and_identity()
    evidence = ROOT / 'artifacts' / 'full-audit-20261113-recheck' / 'platform'
    evidence.mkdir(parents=True, exist_ok=True)
    label = 'recheck_remaining'
    name = 'test_audit_batch_' + label
    manifest = {'targets': TARGETS, 'source_hashes': sources(), 'synthetic_only': True,
                'external_network_forbidden': True, 'original_password_hashers': True,
                'database_strategy': 'WAL_LOG', 'test_database': name}
    (evidence / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    db = psycopg2.connect(host='127.0.0.1', port=config['port'], user='full_audit', dbname='postgres')
    db.autocommit = True
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', [name])
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0 STRATEGY WAL_LOG').format(
                    sql.Identifier(name)))
    finally:
        db.close()
    _, record = execute(label, ['test', *TARGETS, '--noinput', '--keepdb', '--verbosity', '1'],
                        evidence, config)
    raise SystemExit(record['exit_code'])


if __name__ == '__main__':
    main()
