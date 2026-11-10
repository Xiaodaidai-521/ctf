"""Opt-in private-ciphertext bundles; not a complete business recovery or download gate."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
import tracemalloc
from unittest.mock import patch

import psycopg2

from data_security.adapters.persistence import backup as implementation
from data_security.adapters.persistence.backup import PostgresAgeBackup
from data_security.application.crypto_service import CryptoService
from data_security.contracts import (
    BASELINE_LIMITS, AuditReceipt, CipherEnvelope, Environment, KeyPurpose, KeyStatus,
    ObjectContext, ProtectionError, ReasonCode, canonical_bytes,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key, root_key, text
from data_security.tests.test_phase5_codec import binary
from tools.data_security.phase3_backup_cases import BackupFixture


class PrivateBackupFixture(BackupFixture):
    def setUp(self):
        super().setUp()
        self.source_files, self.target_files = self.work / 'source-files', self.work / 'target-files'
        self.source_files.mkdir(mode=0o700)
        self.target_files.mkdir(mode=0o700)
        self.crypto = CryptoService(keys=FakeKeys(), service_identity='private-backup/test', random_bytes=os.urandom,
                                    environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.context = examples()[ObjectContext]
        self.data_key = reference_key()
        data_file = self.work / 'synthetic-data-key'
        data_file.write_bytes(root_key(KeyPurpose.DATA.value))
        data_file.chmod(0o600)
        self.offline_resolver.grants[(self.data_key.key_ref, KeyPurpose.DATA, 'service/backup-offline')] = data_file
        self.rows = []
        with psycopg2.connect(**dict(self.database, dbname=self.source)) as connection:
            with connection.cursor() as cursor:
                cursor.execute('CREATE TABLE security_policies_privateobject ('
                    'object_ref text PRIMARY KEY, ciphertext_hash text NOT NULL, size_bytes bigint NOT NULL, state text NOT NULL)')
                for number, state in ((1, 'candidate'), (2, 'published')):
                    payload = text('synthetic private evidence ' + str(number))
                    sealed = self.crypto.seal(payload, self.context, self.data_key)
                    self.assertIsInstance(sealed, CipherEnvelope)
                    encoded = canonical_bytes(sealed)
                    object_id = str(number) * 64
                    row = ('private/' + object_id, hashlib.sha256(encoded).hexdigest(), len(encoded), state)
                    path = self.source_files / (object_id + '.sealed')
                    path.write_bytes(encoded)
                    path.chmod(0o600)
                    cursor.execute('INSERT INTO security_policies_privateobject VALUES (%s,%s,%s,%s)', row)
                    self.rows.append((row, payload))
        # These are explicit owner-declared restore references, not online secret access.
        self.required = (replace(self.data_key, status=KeyStatus.READ_ONLY),)
        self.checks = self.checks + (('check/private-state',
            'SELECT object_ref, state FROM security_policies_privateobject ORDER BY object_ref'),)
        common = dict(directory=self.work, checks=self.checks, environment=Environment.TEST, domain='domain/backup',
            age=self.tools / 'usr/bin/age', pg_dump=self.repo.parent / '.state/pg-install/bin/pg_dump',
            pg_restore=self.repo.parent / '.state/pg-install/bin/pg_restore', code_version='isolated/phase6',
            required_keys=self.required)
        self.online = PostgresAgeBackup(resolver=self.online_resolver, service_identity='service/backup-online',
            database=dict(self.database, dbname=self.source), private_root=self.source_files, **common)
        self.offline = PostgresAgeBackup(resolver=self.offline_resolver, service_identity='service/backup-offline',
            database=dict(self.database, dbname=self.target), identity_ref=self.private_ref,
            private_root=self.target_files, **common)


class PrivateBackupAcceptance(PrivateBackupFixture):
    def test_retired_rows_remain_in_database_but_do_not_require_deleted_ciphertext(self):
        with psycopg2.connect(**dict(self.database, dbname=self.source)) as connection:
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO security_policies_privateobject VALUES (%s,%s,%s,%s)',
                    ('private/' + '3' * 64, 'a' * 64, 100, 'retired'))
        result = self.create()
        self.assertIsInstance(self.offline.restore(result, self.offline_context), AuditReceipt)
        self.assertEqual(len(list(self.target_files.glob('*.sealed'))), 2)
        with closing(psycopg2.connect(**dict(self.database, dbname=self.target))) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT state FROM security_policies_privateobject ORDER BY object_ref')
                self.assertEqual(cursor.fetchall(), [('candidate',), ('published',), ('retired',)])
        record = json.loads(next(self.work.glob('backup-restore-*.json')).read_text())
        self.assertEqual(record['private_files']['records'], 2)

    def test_database_and_private_ciphertexts_roundtrip_without_publishing_candidates(self):
        result = self.create()
        self.assertEqual(result.version, 'v2')
        receipt = self.offline.restore(result, self.offline_context)
        self.assertIsInstance(receipt, AuditReceipt)
        self.assertIsNone(receipt.chain_version)
        for row, payload in self.rows:
            source = self.source_files / (row[0].removeprefix('private/') + '.sealed')
            restored = self.target_files / source.name
            self.assertEqual(restored.read_bytes(), source.read_bytes())
            self.assertEqual(restored.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.crypto.open(CipherEnvelope.from_json(restored.read_bytes()),
                                             self.context, self.data_key), payload)
        with closing(psycopg2.connect(**dict(self.database, dbname=self.target))) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT state FROM security_policies_privateobject ORDER BY object_ref')
                self.assertEqual(cursor.fetchall(), [('candidate',), ('published',)])
        record = json.loads(next(self.work.glob('backup-restore-*.json')).read_text())
        self.assertEqual(record['private_files']['records'], 2)
        self.assertEqual(record['code_version'], 'isolated/phase6')
        self.assertEqual(record['required_keys'], [key.to_wire() for key in self.required])
        self.assertEqual(self.online_resolver.calls, [
            (self.public_ref.key_ref, KeyPurpose.BACKUP_PUBLIC, 'service/backup-online')])
        self.assertFalse(list(self.work.glob('*.partial')))
        for path in self.work.glob('*.age'):
            self.assertNotIn(b'synthetic private evidence', path.read_bytes())

    def test_file_catalog_and_database_share_snapshot_despite_committed_changes(self):
        measure = implementation._measure
        def mutate(connection, checks):
            result = measure(connection, checks)
            if checks == self.checks:
                with psycopg2.connect(**dict(self.database, dbname=self.source)) as writer:
                    with writer.cursor() as cursor:
                        cursor.execute("UPDATE security_policies_privateobject SET state='changed'")
                        cursor.execute("INSERT INTO security_policies_privateobject VALUES (%s,%s,100,'candidate')",
                                       ('private/' + '3' * 64, 'a' * 64))
                        cursor.execute('UPDATE marker SET generation=2')
            return result
        with patch.object(implementation, '_measure', side_effect=mutate):
            result = self.create()
        self.assertIsInstance(self.offline.restore(result, self.offline_context), AuditReceipt)
        self.assertEqual(len(list(self.target_files.iterdir())), 2)
        with closing(psycopg2.connect(**dict(self.database, dbname=self.target))) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT generation FROM marker')
                self.assertEqual(cursor.fetchone(), (1,))
                cursor.execute('SELECT state FROM security_policies_privateobject ORDER BY object_ref')
                self.assertEqual(cursor.fetchall(), [('candidate',), ('published',)])

    def test_missing_or_changed_source_never_registers_bundle(self):
        path = next(self.source_files.iterdir())
        original = path.read_bytes()
        path.write_bytes(b'X' * len(original))
        changed = self.online.create('snapshot/changed', self.public_ref, self.online_context)
        self.assertEqual(changed.code, ReasonCode.HASH_MISMATCH)
        path.unlink()
        missing = self.online.create('snapshot/missing', self.public_ref, self.online_context)
        self.assertEqual(missing.code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertFalse(list(self.work.glob('*.json')))
        self.assertFalse(list(self.work.glob('*.age')))
        self.assertFalse(list(self.work.glob('*.partial')))

    def test_missing_or_truncated_file_part_fails_before_database_or_file_writes(self):
        result = self.create()
        part = self.work / (result.object_ref.split('/')[1] + '.files.age')
        original = part.read_bytes()
        part.unlink()
        self.assert_no_restore(self.offline.restore(result, self.offline_context))
        self.assertFalse(list(self.target_files.iterdir()))
        part.write_bytes(original[:-1])
        part.chmod(0o600)
        self.assertEqual(self.offline.restore(result, self.offline_context).code, ReasonCode.HASH_MISMATCH)
        self.assertFalse(list(self.target_files.iterdir()))
        self.assert_no_restore(self.offline.restore(result, self.offline_context))

    def test_missing_declared_key_and_wrong_age_identity_fail_before_restore(self):
        result = self.create()
        grant = (self.data_key.key_ref, KeyPurpose.DATA, 'service/backup-offline')
        material = self.offline_resolver.grants.pop(grant)
        failure = self.offline.restore(result, self.offline_context)
        self.assertEqual(failure.code, ReasonCode.KEY_UNAVAILABLE)
        self.assert_no_restore(failure)
        self.assertFalse(list(self.target_files.iterdir()))
        self.offline_resolver.grants[grant] = material
        self.offline_resolver.grants[(self.private_ref.key_ref, KeyPurpose.BACKUP_PRIVATE,
                                      'service/backup-offline')] = self.wrong_identity
        self.assert_no_restore(self.offline.restore(result, self.offline_context))
        self.assertFalse(list(self.target_files.iterdir()))

    def test_code_mismatch_nonempty_files_and_legacy_reader_do_not_restore(self):
        result = self.create()
        self.offline.code_version = 'isolated/other'
        self.assert_no_restore(self.offline.restore(result, self.offline_context))
        self.offline.code_version = 'isolated/phase6'
        marker = self.target_files / 'existing.sealed'
        marker.write_bytes(b'synthetic ciphertext placeholder')
        self.assert_no_restore(self.offline.restore(result, self.offline_context))
        self.assertEqual(marker.read_bytes(), b'synthetic ciphertext placeholder')
        marker.unlink()
        self.offline.private_root = None
        self.assertEqual(self.offline.restore(result, self.offline_context).code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertFalse(list(self.target_files.iterdir()))

    def test_failed_file_encryption_or_database_dump_does_not_register_either_part(self):
        for tool in ('age', 'pg_dump'):
            with self.subTest(tool=tool), patch.object(self.online, tool, '/bin/false'):
                result = self.online.create('snapshot/failure', self.public_ref, self.online_context)
            self.assertIsInstance(result, ProtectionError)
            self.assertFalse(list(self.work.glob('*.json')))
            self.assertFalse(list(self.work.glob('*.age')))
            self.assertFalse(list(self.work.glob('*.partial')))
            self.assertEqual(len(list(self.source_files.iterdir())), 2)

    def test_catalog_mismatch_leaves_only_ciphertexts_without_restore_success(self):
        measure = implementation._measure
        def corrupt_catalog(connection, checks):
            measured = measure(connection, checks)
            if checks == (('files', implementation.FILES_QUERY),):
                measured['files']['records'] += 1
            return measured
        # Inject a bad authenticated manifest, not a skipped comparison in restore.
        with patch.object(implementation, '_measure', side_effect=corrupt_catalog):
            result = self.create()
        failed = self.offline.restore(result, self.offline_context)
        self.assertEqual(failed.code, ReasonCode.REPORT_MISMATCH)
        self.assert_no_restore(failed)
        for source in self.source_files.iterdir():
            restored = self.target_files / source.name
            self.assertEqual(restored.read_bytes(), source.read_bytes())
            self.assertEqual(restored.stat().st_mode & 0o777, 0o600)
        # No cross-resource rollback is claimed; a retry cannot overwrite residuals.
        retry = self.offline.restore(result, self.offline_context)
        self.assertEqual(retry.code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assert_no_restore(retry)

    def test_database_restore_failure_keeps_ciphertexts_and_no_success_record(self):
        result = self.create()
        with patch.object(self.offline, 'pg_restore', '/bin/false'):
            self.assert_no_restore(self.offline.restore(result, self.offline_context))
        self.assertEqual(len(list(self.target_files.iterdir())), 2)
        for source in self.source_files.iterdir():
            self.assertEqual((self.target_files / source.name).read_bytes(), source.read_bytes())
        retry = self.offline.restore(result, self.offline_context)
        self.assertEqual(retry.code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assert_no_restore(retry)

    def test_total_over_twenty_mib_uses_bounded_reads_without_whole_bundle_allocation(self):
        total = 0
        with psycopg2.connect(**dict(self.database, dbname=self.source)) as connection:
            with connection.cursor() as cursor:
                for row, _ in self.rows:
                    payload = binary(os.urandom(9 * 1024 * 1024))
                    sealed = self.crypto.seal(payload, self.context, self.data_key)
                    self.assertIsInstance(sealed, CipherEnvelope)
                    encoded = canonical_bytes(sealed)
                    path = self.source_files / (row[0].removeprefix('private/') + '.sealed')
                    path.write_bytes(encoded)
                    total += len(encoded)
                    cursor.execute('UPDATE security_policies_privateobject SET ciphertext_hash=%s, size_bytes=%s '
                                   'WHERE object_ref=%s', (hashlib.sha256(encoded).hexdigest(), len(encoded), row[0]))
        del payload, sealed, encoded
        self.assertGreater(total, 20 * 1024 * 1024)
        read = implementation._DigestReader.read
        observed = {'calls': 0, 'max_bytes': 0}
        def bounded_read(reader, size):
            self.assertGreater(size, 0)
            self.assertLessEqual(size, implementation.CHUNK)
            observed['calls'] += 1
            observed['max_bytes'] = max(observed['max_bytes'], size)
            return read(reader, size)
        # Trace the adapter only, excluding fixture encryption and verification;
        # this is Python allocation evidence, not aggregate process-tree RSS.
        tracemalloc.start()
        try:
            with patch.object(implementation._DigestReader, 'read', bounded_read):
                started = perf_counter()
                result = self.create()
                created = perf_counter()
                receipt = self.offline.restore(result, self.offline_context)
                restored_at = perf_counter()
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertIsInstance(receipt, AuditReceipt)
        self.assertGreater(observed['calls'], 2)
        self.assertLess(peak, total // 4)
        for source in self.source_files.iterdir():
            with source.open('rb') as left, (self.target_files / source.name).open('rb') as right:
                self.assertEqual(hashlib.file_digest(left, 'sha256').digest(),
                                 hashlib.file_digest(right, 'sha256').digest())
        files_part = self.work / (result.object_ref.split('/')[1] + '.files.age')
        self.assertGreater(files_part.stat().st_size, 20 * 1024 * 1024)
        observation = {'scope': 'adapter-only Python allocations; not business-chain or process-tree RSS',
            'private_ciphertext_bytes': total, 'database_age_bytes': result.size_bytes,
            'files_age_bytes': files_part.stat().st_size, 'python_peak_allocated_bytes': peak,
            'create_seconds': created - started, 'restore_seconds': restored_at - created,
            'bounded_reads': observed, 'complete_business_recovery': False}
        with (self.controlled / 'private-backup-observations.json').open('x') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(observation, stream, indent=2)
            stream.write('\n')

    def test_formal_v2_bootstrap_validates_explicit_options_and_restores_with_file_keys(self):
        import django
        from ctf_backend.security_bootstrap import assemble
        from data_security.adapters.keys import FileKeyResolver
        from data_security.contracts import ContractViolation, KeyReference
        from data_security.tests.phase3_fixtures import configuration

        os.environ.update(DB_HOST='127.0.0.1', DB_PORT=str(self.database['port']),
                          DB_USER=self.database['user'], DB_NAME=self.source, DB_PASSWORD='')
        django.setup()
        with configuration(providers=()) as fixture:
            path, config = fixture[:2]
            recipient = path.parent / 'backup-recipient.key'
            recipient.write_bytes(self.recipient_file.read_bytes())
            recipient.chmod(0o600)
            manifest_path = Path(config['key_manifest'])
            manifest = json.loads(manifest_path.read_text())
            manifest['entries'].append({'reference': self.public_ref.to_wire(),
                'file': recipient.name, 'identities': ['service/security']})
            manifest_path.write_text(json.dumps(manifest))
            self.assertNotIn(KeyPurpose.BACKUP_PRIVATE.value,
                             [entry['reference']['purpose'] for entry in manifest['entries']])
            options = dict(database=dict(self.database, host='127.0.0.1', dbname=self.source, password=''),
                directory=str(self.work), checks=self.checks, age=str(self.tools / 'usr/bin/age'),
                pg_dump=str(self.repo.parent / '.state/pg-install/bin/pg_dump'),
                pg_restore=str(self.repo.parent / '.state/pg-install/bin/pg_restore'),
                private_root=str(self.source_files), code_version='isolated/phase6',
                required_keys=[key.to_wire() for key in self.required])
            config['backup'] = options
            path.write_text(json.dumps(config))
            with self.assertRaises(ContractViolation):
                assemble(config_path=path)  # v1 never enables private bundles implicitly.
            config.update(schema_version='ds.bootstrap.v2', policy_repository={'kind': 'file', 'writable': False})
            for missing in ('private_root', 'code_version', 'required_keys'):
                with self.subTest(missing=missing):
                    config['backup'] = {name: value for name, value in options.items() if name != missing}
                    path.write_text(json.dumps(config))
                    with self.assertRaises(ContractViolation):
                        assemble(config_path=path)
            for field, value in (('private_root', None), ('required_keys', {}), ('required_keys', []),
                                 ('required_keys', [{'schema_version': 'invalid'}]), ('implementation', 'arbitrary.Backup')):
                with self.subTest(field=field, value=value):
                    config['backup'] = {**options, field: value}
                    path.write_text(json.dumps(config))
                    with self.assertRaises((ContractViolation, ValueError)):
                        assemble(config_path=path)
            config['backup'] = {name: value for name, value in options.items()
                                if name not in ('private_root', 'code_version', 'required_keys')}
            path.write_text(json.dumps(config))
            self.assertIsNone(assemble(config_path=path)['backup'].private_root)
            config['backup'] = options
            path.write_text(json.dumps(config))
            components = assemble(config_path=path)
            online = components['backup']
            self.assertIs(type(online), PostgresAgeBackup)
            self.assertIs(type(online.resolver), FileKeyResolver)
            self.assertIsNone(online.identity_ref)
            self.assertEqual(online.private_root, self.source_files)
            self.assertEqual(online.required_keys, self.required)
            self.assertIsInstance(online.resolver.resolve(self.private_ref, KeyPurpose.BACKUP_PRIVATE,
                                                         'service/security'), ProtectionError)
            object_context = replace(self.context, environment=Environment.EVALUATION)
            with psycopg2.connect(**dict(self.database, dbname=self.source)) as connection:
                with connection.cursor() as cursor:
                    for row, payload in self.rows:
                        sealed = components['crypto'].seal(payload, object_context, components['data_ref'])
                        self.assertIsInstance(sealed, CipherEnvelope)
                        encoded = canonical_bytes(sealed)
                        (self.source_files / (row[0].removeprefix('private/') + '.sealed')).write_bytes(encoded)
                        cursor.execute('UPDATE security_policies_privateobject SET ciphertext_hash=%s, size_bytes=%s '
                                       'WHERE object_ref=%s', (hashlib.sha256(encoded).hexdigest(), len(encoded), row[0]))
            offline_root = self.work / 'formal-offline'
            offline_root.mkdir(mode=0o700)
            offline_root.chmod(0o700)
            entries = []
            for name, source, ref in (('identity', self.identity, self.private_ref),
                                      ('data', path.parent / 'data_key.key', self.required[0])):
                target = offline_root / name
                target.write_bytes(source.read_bytes())
                target.chmod(0o600)
                entries.append({'reference': ref.to_wire(), 'file': name, 'identities': ['service/backup-offline']})
            offline_manifest = offline_root / 'manifest.json'
            offline_manifest.write_text(json.dumps({'schema_version': 'ds.key-manifest.v1',
                'environment': 'evaluation', 'entries': entries}))
            offline_manifest.chmod(0o600)
            resolver = FileKeyResolver(manifest_path=offline_manifest, environment=Environment.EVALUATION,
                                       repository_root=self.repo.parent)
            offline = PostgresAgeBackup(resolver=resolver, service_identity='service/backup-offline',
                database=dict(options['database'], dbname=self.target), directory=self.work, checks=self.checks,
                environment=Environment.EVALUATION, domain='ctf', age=Path(options['age']),
                pg_dump=Path(options['pg_dump']), pg_restore=Path(options['pg_restore']), identity_ref=self.private_ref,
                private_root=self.target_files, code_version=options['code_version'], required_keys=self.required)
            context = replace(self.online_context, actor_ref='service/security',
                              environment=Environment.EVALUATION, domain='ctf')
            result = online.create('snapshot/formal-private', self.public_ref, context)
            self.assertEqual(result.version, 'v2')
            receipt = offline.restore(result, replace(context, actor_ref='service/backup-offline'))
            self.assertIsInstance(receipt, AuditReceipt)
            self.assertIsNone(receipt.chain_version)
            crypto = CryptoService(keys=resolver, service_identity='service/backup-offline', random_bytes=os.urandom,
                                   environment=Environment.EVALUATION, limits=BASELINE_LIMITS)
            for row, payload in self.rows:
                restored = self.target_files / (row[0].removeprefix('private/') + '.sealed')
                self.assertEqual(crypto.open(CipherEnvelope.from_json(restored.read_bytes()),
                                             object_context, self.required[0]), payload)
            self.assertIsInstance(resolver.resolve(KeyReference.from_wire(config['data_key']), KeyPurpose.DATA,
                                                   'service/security'), ProtectionError)
