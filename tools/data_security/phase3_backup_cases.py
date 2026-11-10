"""Real PostgreSQL + age acceptance. Run via tools.data_security.phase3_backup_verify.

The explicit opt-in prevents ordinary tests touching any database or key material.
All key files live outside the worktree and outside the evidence directory.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg2
from psycopg2 import sql

from data_security.adapters.persistence import backup as implementation
from data_security.adapters.persistence.backup import PostgresAgeBackup
from data_security.contracts import (AuditReceipt, Environment, KeyPurpose, KeyReference,
    KeyStatus, ProtectionContext, ProtectionError, Purpose, ReasonCode, SecretMaterial, StoredObject)
from data_security.tests.fixtures import dto, examples


class IsolatedResolver:
    """Test only: explicit per-service grants; never acceptable to B."""
    def __init__(self, grants):
        self.grants = grants
        self.calls = []

    def resolve(self, ref, purpose, service_identity):
        self.calls.append((ref.key_ref, purpose, service_identity))
        path = self.grants.get((ref.key_ref, purpose, service_identity))
        if path is None:
            return dto(ProtectionError, code=ReasonCode.KEY_UNAVAILABLE,
                       retryable=False, trace_id='trace/backup-resolver')
        return SecretMaterial(path.read_bytes().strip(), purpose)


class BackupFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('DS_PHASE3_BACKUP_RUN') != '1':
            raise RuntimeError('EXPLICIT_ISOLATED_BACKUP_ACCEPTANCE_REQUIRED')
        cls.repo = Path(__file__).resolve().parents[2] / 'backend'
        cluster = json.loads((cls.repo.parent / '.state/postgres.json').read_text())
        if not cluster['synthetic_only'] or cluster['socket'] != str(cls.repo.parent / '.state/pg-run'):
            raise RuntimeError('DEDICATED_SYNTHETIC_CLUSTER_REQUIRED')
        cls.database = dict(host=cluster['socket'], port=cluster['port'], user=cluster['user'],
                            dbname='postgres', sslmode='disable')
        cls.tools = Path(os.environ['DS_PHASE3_TOOLS'])
        cls.controlled = Path(os.environ['DS_PHASE3_CONTROLLED'])
        if cls.controlled.is_relative_to(cls.repo.parent) or cls.controlled.stat().st_mode & 0o077:
            raise RuntimeError('EXTERNAL_CONTROLLED_DIRECTORY_REQUIRED')
        cls.online_keys = cls.controlled / 'online'
        cls.offline_keys = cls.controlled / 'offline'
        cls.online_keys.mkdir(mode=0o700)
        cls.offline_keys.mkdir(mode=0o700)
        cls.identity = cls.offline_keys / 'identity'
        cls.wrong_identity = cls.offline_keys / 'wrong-identity'
        cls.recipient_file = cls.online_keys / 'recipient'
        for identity in (cls.identity, cls.wrong_identity):
            subprocess.run([str(cls.tools / 'usr/bin/age-keygen'), '-o', str(identity)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            # age-keygen includes comments; only the one identity line enters M5 material.
            value = next(line for line in identity.read_bytes().splitlines() if line.startswith(b'AGE-'))
            identity.write_bytes(value + b'\n')
            identity.chmod(0o600)
        with cls.recipient_file.open('wb') as output:
            subprocess.run([str(cls.tools / 'usr/bin/age-keygen'), '-y', str(cls.identity)],
                           stdout=output, stderr=subprocess.DEVNULL, check=True)
        cls.recipient_file.chmod(0o600)
        cls.public_ref = dto(KeyReference, key_ref='backup-recipient/v1', purpose=KeyPurpose.BACKUP_PUBLIC,
                             version='v1', status=KeyStatus.ACTIVE)
        cls.private_ref = dto(KeyReference, key_ref='backup-identity/v1', purpose=KeyPurpose.BACKUP_PRIVATE,
                              version='v1', status=KeyStatus.READ_ONLY)
        cls.checks = (('check/items', 'SELECT id, value FROM items ORDER BY id'),
                      ('check/marker', 'SELECT generation FROM marker ORDER BY generation'))

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix='objects-', dir=self.controlled))
        self.source = 'phase3_backup_src_' + uuid4().hex[:12]
        self.target = 'phase3_backup_dst_' + uuid4().hex[:12]
        with closing(psycopg2.connect(**self.database)) as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.source)))
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.target)))
        self.addCleanup(self.clean_databases)
        with psycopg2.connect(**dict(self.database, dbname=self.source)) as connection:
            with connection.cursor() as cursor:
                cursor.execute('CREATE TABLE items (id integer PRIMARY KEY, value text NOT NULL)')
                cursor.execute("INSERT INTO items SELECT i, repeat(md5(i::text), 32) FROM generate_series(1,4096) i")
                cursor.execute('CREATE TABLE marker (generation integer NOT NULL)')
                cursor.execute('INSERT INTO marker VALUES (1)')
        self.online_resolver = IsolatedResolver({
            (self.public_ref.key_ref, KeyPurpose.BACKUP_PUBLIC, 'service/backup-online'): self.recipient_file})
        self.offline_resolver = IsolatedResolver({
            (self.private_ref.key_ref, KeyPurpose.BACKUP_PRIVATE, 'service/backup-offline'): self.identity})
        common = dict(directory=self.work, checks=self.checks, environment=Environment.TEST, domain='domain/backup',
            age=self.tools / 'usr/bin/age', pg_dump=self.repo.parent / '.state/pg-install/bin/pg_dump',
            pg_restore=self.repo.parent / '.state/pg-install/bin/pg_restore')
        self.online = PostgresAgeBackup(resolver=self.online_resolver, service_identity='service/backup-online',
            database=dict(self.database, dbname=self.source), **common)
        self.offline = PostgresAgeBackup(resolver=self.offline_resolver, service_identity='service/backup-offline',
            database=dict(self.database, dbname=self.target), identity_ref=self.private_ref, **common)
        context = examples()[ProtectionContext]
        self.online_context = replace(context, actor_ref='service/backup-online',
                                      purpose=Purpose.STORAGE, domain='domain/backup')
        self.offline_context = replace(self.online_context, actor_ref='service/backup-offline')

    def clean_databases(self):
        connection = psycopg2.connect(**self.database)
        connection.autocommit = True
        try:
            with connection.cursor() as cursor:
                for name in (self.source, self.target):
                    assert re.fullmatch(r'phase3_backup_(src|dst)_[0-9a-f]{12}', name)
                    cursor.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        finally:
            connection.close()
        shutil.rmtree(self.work)

    def create(self):
        result = self.online.create('snapshot/synthetic', self.public_ref, self.online_context)
        self.assertIsInstance(result, StoredObject)
        return result

    def assert_no_restore(self, result):
        self.assertIsInstance(result, ProtectionError)
        self.assertFalse(list(self.work.glob('backup-restore-*.json')))
        with psycopg2.connect(**dict(self.database, dbname=self.target)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.items')")
                self.assertIsNone(cursor.fetchone()[0])


class BackupAcceptance(BackupFixture):
    def test_round_trip_manifest_counts_digest_and_permissions(self):
        result = self.create()
        receipt = self.offline.restore(result, self.offline_context)
        self.assertIsInstance(receipt, AuditReceipt)
        record = json.loads(next(self.work.glob('backup-restore-*.json')).read_text())
        self.assertEqual(record['checks']['check/items']['records'], 4096)
        self.assertEqual(record['checks']['check/marker']['records'], 1)
        self.assertIn(':', record['consistency_point'])
        self.assertEqual(receipt.durability.value, 'durable')
        self.assertIsNone(receipt.chain_version)
        self.assertEqual(self.online_resolver.calls, [
            ('backup-recipient/v1', KeyPurpose.BACKUP_PUBLIC, 'service/backup-online')])
        self.assertEqual(self.offline_resolver.calls, [
            ('backup-identity/v1', KeyPurpose.BACKUP_PRIVATE, 'service/backup-offline')])
        self.assertTrue(all(path.stat().st_mode & 0o077 == 0 for path in self.work.iterdir()))
        self.assertFalse(list(self.work.glob('*.partial')))
        # Only count/digest/consistency metadata crosses into E3, not decrypted rows.
        observation = {'checks': record['checks'], 'consistency_point': record['consistency_point'],
                       'ciphertext_sha256': result.ciphertext_hash, 'ciphertext_bytes': result.size_bytes,
                       'receipt_durability': receipt.durability.value}
        (self.controlled / 'observations.json').write_text(json.dumps(observation, sort_keys=True))
        (self.controlled / 'observations.json').chmod(0o600)

    def test_snapshot_survives_committed_changes_during_dump(self):
        measure = implementation._measure
        def concurrent_change(connection, checks):
            result = measure(connection, checks)
            with psycopg2.connect(**dict(self.database, dbname=self.source)) as writer:
                with writer.cursor() as cursor:
                    cursor.execute("UPDATE items SET value='changed' WHERE id=1")
                    cursor.execute('UPDATE marker SET generation=2')
            return result
        with patch.object(implementation, '_measure', side_effect=concurrent_change):
            result = self.create()
        self.assertIsInstance(self.offline.restore(result, self.offline_context), AuditReceipt)
        with psycopg2.connect(**dict(self.database, dbname=self.target)) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT generation FROM marker')
                self.assertEqual(cursor.fetchone(), (1,))

    def test_formal_bootstrap_and_file_resolvers_restore_to_empty_database(self):
        import django
        from data_security.adapters.keys import FileKeyResolver
        from data_security.tests.phase3_fixtures import configuration

        # Configure the real Django app for this synthetic database, not a test B.
        os.environ.update(DB_HOST='127.0.0.1', DB_PORT=str(self.database['port']),
                          DB_USER=self.database['user'], DB_NAME=self.source, DB_PASSWORD='')
        django.setup()
        from ctf_backend.security_bootstrap import assemble

        with configuration(providers=()) as fixture:
            config_path, config = fixture[:2]
            online_directory = config_path.parent
            public_file = online_directory / 'backup-recipient.key'
            public_file.write_bytes(self.recipient_file.read_bytes())
            public_file.chmod(0o600)
            online_manifest = Path(config['key_manifest'])
            document = json.loads(online_manifest.read_text())
            document['entries'].append({'reference': self.public_ref.to_wire(),
                'file': public_file.name, 'identities': ['service/security']})
            online_manifest.write_text(json.dumps(document))
            online_manifest.chmod(0o600)
            self.assertNotIn(KeyPurpose.BACKUP_PRIVATE.value,
                [entry['reference']['purpose'] for entry in document['entries']])
            config['backup'] = {
                'database': dict(self.database, host='127.0.0.1', dbname=self.source, password=''),
                'directory': str(self.work), 'checks': self.checks,
                'age': str(self.tools / 'usr/bin/age'),
                'pg_dump': str(self.repo.parent / '.state/pg-install/bin/pg_dump'),
                'pg_restore': str(self.repo.parent / '.state/pg-install/bin/pg_restore')}
            config_path.write_text(json.dumps(config))
            online = assemble(config_path=config_path)['backup']
            self.assertIs(type(online), PostgresAgeBackup)
            self.assertIs(type(online.resolver), FileKeyResolver)
            self.assertIsNone(online.identity_ref)
            self.assertIsInstance(online.resolver.resolve(self.private_ref, KeyPurpose.BACKUP_PRIVATE,
                                                         'service/security'), ProtectionError)

            offline_directory = self.controlled / 'formal-offline'
            offline_directory.mkdir(mode=0o700)
            offline_directory.chmod(0o700)  # Clear inherited setgid as required by M5.
            private_file = offline_directory / 'backup-identity.key'
            private_file.write_bytes(self.identity.read_bytes())
            private_file.chmod(0o600)
            offline_manifest = offline_directory / 'manifest.json'
            offline_manifest.write_text(json.dumps({'schema_version': 'ds.key-manifest.v1',
                'environment': 'evaluation', 'entries': [{'reference': self.private_ref.to_wire(),
                    'file': private_file.name, 'identities': ['service/backup-offline']}]}))
            offline_manifest.chmod(0o600)
            resolver = FileKeyResolver(manifest_path=offline_manifest,
                environment=Environment.EVALUATION, repository_root=self.repo.parent)
            self.assertIsInstance(resolver.resolve(self.private_ref, KeyPurpose.BACKUP_PRIVATE,
                                                    'service/security'), ProtectionError)
            self.assertIsInstance(resolver.resolve(self.public_ref, KeyPurpose.BACKUP_PUBLIC,
                                                    'service/backup-offline'), ProtectionError)
            offline = PostgresAgeBackup(resolver=resolver, service_identity='service/backup-offline',
                database=dict(self.database, host='127.0.0.1', dbname=self.target, password=''),
                directory=self.work, checks=self.checks, environment=Environment.EVALUATION,
                domain='ctf', age=self.tools / 'usr/bin/age',
                pg_dump=self.repo.parent / '.state/pg-install/bin/pg_dump',
                pg_restore=self.repo.parent / '.state/pg-install/bin/pg_restore', identity_ref=self.private_ref)
            context = replace(self.online_context, actor_ref='service/security',
                              environment=Environment.EVALUATION, domain='ctf')
            result = online.create('snapshot/formal-synthetic', self.public_ref, context)
            self.assertIsInstance(result, StoredObject)
            receipt = offline.restore(result, replace(context, actor_ref='service/backup-offline'))
            self.assertIsInstance(receipt, AuditReceipt)
            record = json.loads(next(self.work.glob('backup-restore-*.json')).read_text())
            self.assertEqual(record['checks']['check/items']['records'], 4096)
            self.assertEqual(record['checks']['check/marker']['records'], 1)
            self.assertEqual(receipt.durability.value, 'durable')
            self.assertIsNone(receipt.chain_version)
            observation = {'assembly': 'ctf_backend.security_bootstrap.assemble',
                'online_resolver': 'FileKeyResolver', 'offline_resolver': 'FileKeyResolver',
                'online_manifest_contains_private_identity': False, 'offline_manifest_private_only': True,
                'service_identity_separation_verified': True, 'secret_file_mode': '0600',
                'checks': record['checks'], 'consistency_point': record['consistency_point'],
                'ciphertext_sha256': result.ciphertext_hash, 'ciphertext_bytes': result.size_bytes,
                'receipt_durability': receipt.durability.value}
            (self.controlled / 'formal-observations.json').write_text(json.dumps(observation, sort_keys=True))
            (self.controlled / 'formal-observations.json').chmod(0o600)

    def test_missing_public_key_no_success_or_artifact(self):
        self.online_resolver.grants.clear()
        result = self.online.create('snapshot/missing', self.public_ref, self.online_context)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_missing_private_key_no_restore(self):
        result = self.create()
        self.offline_resolver.grants.clear()
        self.assert_no_restore(self.offline.restore(result, self.offline_context))

    def test_wrong_private_key_no_restore(self):
        result = self.create()
        self.offline_resolver.grants[next(iter(self.offline_resolver.grants))] = self.wrong_identity
        self.assert_no_restore(self.offline.restore(result, self.offline_context))

    def test_truncated_ciphertext_even_with_recomputed_outer_digest(self):
        result = self.create()
        path = self.work / (result.object_ref.split('/')[1] + '.age')
        with path.open('r+b') as stream:
            stream.truncate(result.size_bytes - 20)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        forged = replace(result, size_bytes=path.stat().st_size, ciphertext_hash=digest)
        self.assert_no_restore(self.offline.restore(forged, self.offline_context))

    def test_export_failure_no_registration(self):
        self.online.pg_dump = '/bin/false'
        result = self.online.create('snapshot/export-failure', self.public_ref, self.online_context)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_encryption_failure_no_registration(self):
        self.online.age = '/bin/false'
        result = self.online.create('snapshot/encrypt-failure', self.public_ref, self.online_context)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_missing_executable_no_registration(self):
        self.online.age = str(self.work / 'missing-age')
        result = self.online.create('snapshot/missing-tool', self.public_ref, self.online_context)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_restore_command_failure_no_success(self):
        result = self.create()
        self.offline.pg_restore = '/bin/false'
        self.assert_no_restore(self.offline.restore(result, self.offline_context))

    def test_online_cannot_restore_offline_cannot_create(self):
        result = self.create()
        self.assert_no_restore(self.online.restore(result, self.online_context))
        denied = self.offline.create('snapshot/forbidden', self.public_ref, self.offline_context)
        self.assertIsInstance(denied, ProtectionError)
        self.assertFalse(self.offline_resolver.calls)

    def test_secret_material_never_enters_process_arguments(self):
        launch = subprocess.Popen
        with patch.object(implementation.subprocess, 'Popen', wraps=launch) as captured:
            result = self.create()
            self.assertIsInstance(self.offline.restore(result, self.offline_context), AuditReceipt)
        arguments = repr([call.args for call in captured.call_args_list]).encode()
        self.assertFalse(self.identity.read_bytes().strip() in arguments)
        self.assertFalse(self.recipient_file.read_bytes().strip() in arguments)
        self.assertFalse(b'password=' in arguments)

    def test_wrong_service_context_no_key_access(self):
        result = self.online.create('snapshot/forbidden', self.public_ref, self.offline_context)
        self.assertIsInstance(result, ProtectionError)
        self.assertFalse(self.online_resolver.calls)

    def test_nonempty_target_is_not_overwritten(self):
        result = self.create()
        with psycopg2.connect(**dict(self.database, dbname=self.target)) as connection:
            with connection.cursor() as cursor:
                cursor.execute('CREATE TABLE already_here(id integer)')
        self.assert_no_restore(self.offline.restore(result, self.offline_context))

    def test_restore_projection_mismatch_no_success(self):
        result = self.create()
        self.offline.checks = (('check/items', 'SELECT id, value FROM items WHERE id < 5 ORDER BY id'),
                               self.checks[1])
        failed = self.offline.restore(result, self.offline_context)
        self.assertIsInstance(failed, ProtectionError)
        self.assertEqual(failed.code, ReasonCode.REPORT_MISMATCH)
        self.assertFalse(list(self.work.glob('backup-restore-*.json')))
