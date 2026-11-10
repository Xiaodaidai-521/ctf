"""M6 PostgreSQL/age adapter. B supplies connections, references and service identity.

Online instances have only a recipient resolver. Offline restore is a separate
instance with a separately authorized identity reference. No secret file lookup,
SQL staging file, shell pipeline, SDK crypto, or unbounded backup read occurs here.
The default v1 remains database-only. Explicit v2 bundles add an age-encrypted
USTAR snapshot of the M6 immutable private objects, bound by the database manifest.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import stat
import subprocess
import tarfile
from contextlib import ExitStack, closing, suppress
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg2
from psycopg2 import sql

from data_security.contracts import Limits
from data_security.contracts.crypto import KeyReference
from data_security.contracts.enums import Durability, KeyPurpose, Purpose, ReasonCode, Role
from data_security.contracts.events import AuditReceipt, ProtectionError
from data_security.contracts.ports import BackupRetentionRecord, KeyResolverPort, StoredObject
from data_security.contracts.schema import ContractViolation, reference, require


CHUNK = 64 * 1024
MAGIC = b'DS-PG-AGE-1\n'
FILES_QUERY = ('SELECT object_ref, ciphertext_hash, size_bytes '
               "FROM security_policies_privateobject WHERE state <> 'retired' ORDER BY object_ref")


class _DigestReader:
    """Hash exactly the bounded reads consumed by the streaming tar writer."""
    def __init__(self, source):
        self.source = source
        self.digest = hashlib.sha256()

    def read(self, size):
        chunk = self.source.read(size)
        self.digest.update(chunk)
        return chunk


def _measure(connection, queries):
    """B-approved ordered projections; server cursor keeps row count bounded."""
    result = {}
    for name, query in queries:
        digest = hashlib.sha256()
        count = 0
        with connection.cursor(name='backup_' + uuid4().hex) as cursor:
            cursor.itersize = 256
            cursor.execute(query)
            for row in cursor:
                encoded = json.dumps(row, ensure_ascii=True, separators=(',', ':'),
                                     default=str).encode('ascii')
                digest.update(struct.pack('!Q', len(encoded)))
                digest.update(encoded)
                count += 1
        result[name] = {'records': count, 'sha256': digest.hexdigest()}
    return result


def _schema_checks(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT LIKE 'pg_%' "
                       "AND schemaname <> 'information_schema' ORDER BY schemaname, tablename")
        tables = cursor.fetchall()
    return tuple(('table/' + schema + '/' + table,
        sql.SQL('SELECT row_to_json(t)::text FROM {}.{} t ORDER BY row_to_json(t)::text').format(
            sql.Identifier(schema), sql.Identifier(table)).as_string(connection)) for schema, table in tables)


def _file_measure(rows):
    digest, count = hashlib.sha256(), 0
    for row in rows:
        encoded = json.dumps(row, ensure_ascii=True, separators=(',', ':')).encode('ascii')
        digest.update(struct.pack('!Q', len(encoded)))
        digest.update(encoded)
        count += 1
    return {'records': count, 'sha256': digest.hexdigest()}


class PostgresAgeBackup:
    """Trusted construction only, not a path/SQL/DSN endpoint for business callers.

    database: libpq keyword arguments from B (no URI in subprocess argv).
    checks: nonempty tuple of (reference, deterministic ordered SELECT), approved
        by the data owner. The manifest records hashes/counts, never row values.
    identity_ref=None: online create only. Non-None: offline restore only.
    Directory must already be owned by this service and mode 0700. Restore must
    target an empty, isolated database; opening it to traffic is not this port's job.
    """

    def __init__(self, *, resolver: KeyResolverPort, service_identity: str,
                 database: dict, directory: Path, checks: tuple, environment,
                 domain: str, age: Path, pg_dump: Path, pg_restore: Path,
                 identity_ref: KeyReference | None = None, private_root: Path | None = None,
                 code_version: str | None = None, required_keys: tuple[KeyReference, ...] = (),
                 full_inventory=False, limits: Limits | None = None,
                 clock=lambda: datetime.now(timezone.utc)):
        reference(service_identity)
        reference(domain)
        self.directory = Path(directory).resolve(strict=True)
        info = self.directory.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('BACKUP_DIRECTORY_PERMISSIONS')
        if not checks or len(checks) > 128 or len(dict(checks)) != len(checks):
            raise ValueError('BACKUP_CHECKS_REQUIRED')
        for name, _ in checks:
            reference(name)
        if identity_ref is not None and identity_ref.purpose is not KeyPurpose.BACKUP_PRIVATE:
            raise ValueError('BACKUP_IDENTITY_PURPOSE')
        self.resolver = resolver
        self.service_identity = service_identity
        self.database = dict(database)
        self.source_identity = hashlib.sha256(json.dumps({
            'database': {name: database.get(name) for name in ('host', 'port', 'dbname')},
            'private_root': str(private_root)}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.checks = checks
        self.environment = environment
        self.domain = domain
        self.age, self.pg_dump, self.pg_restore = map(str, (age, pg_dump, pg_restore))
        self.identity_ref = identity_ref
        self.private_root = None
        if private_root is not None:
            if environment.value not in ('test', 'evaluation'):
                raise ValueError('ISOLATED_PRIVATE_BACKUP_REQUIRED')
            reference(code_version)
            if not required_keys or len(required_keys) > 128 or any(type(key) is not KeyReference for key in required_keys):
                raise ValueError('BACKUP_REQUIRED_KEY_REFERENCES')
            root = Path(private_root)
            info = root.lstat()
            if (not root.is_absolute() or root != root.resolve() or not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != os.getuid() or info.st_mode & 0o077):
                raise ValueError('BACKUP_PRIVATE_DIRECTORY_PERMISSIONS')
            self.private_root = root
        elif code_version is not None or required_keys:
            raise ValueError('BACKUP_PRIVATE_ROOT_REQUIRED')
        require(type(full_inventory) is bool and (not full_inventory or
                (self.private_root is not None and type(limits) is Limits)), ReasonCode.INVALID_VALUE)
        self.full_inventory, self.limits = full_inventory, limits
        self.code_version, self.required_keys = code_version, required_keys
        self.clock = clock
        # Do not inherit ambient PGPASSWORD/PGSERVICE/PGOPTIONS or send a DSN in argv.
        names = {'host': 'PGHOST', 'port': 'PGPORT', 'dbname': 'PGDATABASE',
                 'user': 'PGUSER', 'password': 'PGPASSWORD', 'sslmode': 'PGSSLMODE',
                 'sslrootcert': 'PGSSLROOTCERT', 'sslcert': 'PGSSLCERT',
                 'sslkey': 'PGSSLKEY', 'connect_timeout': 'PGCONNECT_TIMEOUT'}
        if set(database) - names.keys():
            raise ValueError('BACKUP_CONNECTION_OPTIONS')
        self.pg_env = {names[key]: str(value) for key, value in database.items()}
        self.pg_env['PATH'] = os.defpath
        self.pg_env['LC_ALL'] = 'C'

    def _allowed(self, context):
        return (context.actor_ref == self.service_identity and context.role is Role.SERVICE
                and context.purpose is Purpose.STORAGE and context.environment is self.environment
                and context.domain == self.domain)

    @staticmethod
    def _error(context, code):
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=context.trace_id)

    def create(self, snapshot_ref, recipient, context, *, cadence=None):
        reference(snapshot_ref)
        if self.identity_ref is not None or not self._allowed(context):
            return self._error(context, ReasonCode.AUTHORIZATION_DENIED)
        if cadence is not None and (cadence not in ('daily', 'weekly') or self.private_root is None):
            return self._error(context, ReasonCode.INVALID_VALUE)
        started_at = self.clock() if cadence is not None else None
        material = self.resolver.resolve(recipient, KeyPurpose.BACKUP_PUBLIC, self.service_identity)
        if isinstance(material, ProtectionError):
            return material
        object_id = uuid4().hex
        partial = self.directory / (object_id + '.partial')
        final = self.directory / (object_id + '.age')
        files_partial = self.directory / (object_id + '.files.partial')
        files_final = self.directory / (object_id + '.files.age')
        version = 'v2' if self.private_root is not None else 'v1'
        processes = []
        try:
            with ExitStack() as stack:
                key_fd = os.memfd_create('backup-recipient', os.MFD_CLOEXEC)
                stack.callback(os.close, key_fd)
                public = bytes(material.borrow(KeyPurpose.BACKUP_PUBLIC)).strip()
                # Accept only native age X25519 public recipients, never identity/plugin input.
                if not re.fullmatch(rb'age1[0-9a-z]{58}', public):
                    return self._error(context, ReasonCode.KEY_UNAVAILABLE)
                os.write(key_fd, public + b'\n')
                os.lseek(key_fd, 0, os.SEEK_SET)
                connection = stack.enter_context(closing(psycopg2.connect(**self.database)))
                connection.set_session(isolation_level='REPEATABLE READ', readonly=True)
                snapshot_at = self.clock()
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_export_snapshot(), txid_current_snapshot()::text')
                    snapshot, consistency = cursor.fetchone()
                manifest = {'format': 'ds.pg-age.v1', 'snapshot_ref': snapshot_ref,
                            'consistency_point': consistency, 'snapshot_id': snapshot,
                            'environment': context.environment.value, 'domain': context.domain,
                            'recipient_ref': recipient.key_ref, 'checks': _measure(connection, self.checks)}
                if self.private_root is not None:
                    manifest.update(format='ds.pg-age.v2', code_version=self.code_version,
                        required_keys=[key.to_wire() for key in self.required_keys],
                        private_files=_measure(connection, (('files', FILES_QUERY),))['files'])
                    pending = ()
                    if self.full_inventory:
                        pending = self._pending_files(connection)
                        manifest['full_inventory'] = {
                            'snapshot_at': snapshot_at.isoformat(), 'recipient': recipient.to_wire(),
                            'source_identity': self.source_identity,
                            'schema': _measure(connection, _schema_checks(connection)),
                            'pending_files': _file_measure(pending)}
                    # Both streams use this same exported snapshot. Files are immutable;
                    # a missing or altered referenced file aborts the entire bundle.
                    with os.fdopen(os.open(files_partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
                        files_encrypt = subprocess.Popen(
                            [self.age, '--encrypt', '--recipients-file', f'/proc/self/fd/{key_fd}'],
                            stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL, pass_fds=(key_fd,))
                        processes.append(files_encrypt)
                        with tarfile.open(fileobj=files_encrypt.stdin, mode='w|', format=tarfile.USTAR_FORMAT) as archive:
                            with connection.cursor(name='files_' + object_id) as cursor:
                                cursor.itersize = 256
                                cursor.execute(FILES_QUERY)
                                for object_ref, ciphertext_hash, size_bytes in cursor:
                                    if (not re.fullmatch(r'private/[0-9a-f]{64}', object_ref)
                                            or not re.fullmatch(r'[0-9a-f]{64}', ciphertext_hash)
                                            or type(size_bytes) is not int or size_bytes < 0):
                                        return self._error(context, ReasonCode.INVALID_VALUE)
                                    path = self.private_root / (object_ref.removeprefix('private/') + '.sealed')
                                    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
                                        info = os.fstat(source.fileno())
                                        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                                                or info.st_mode & 0o077 or info.st_size != size_bytes):
                                            return self._error(context, ReasonCode.SOURCE_NOT_APPROVED)
                                        member = tarfile.TarInfo(object_ref + '/' + ciphertext_hash)
                                        member.size, member.mode = size_bytes, 0o600
                                        reader = _DigestReader(source)
                                        archive.addfile(member, reader)
                                        archive.members.clear()
                                        if reader.digest.hexdigest() != ciphertext_hash:
                                            return self._error(context, ReasonCode.HASH_MISMATCH)
                            for object_ref, ciphertext_hash, size_bytes in pending:
                                path = self.private_root / (object_ref.removeprefix('private/') + '.sealed')
                                with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
                                    member = tarfile.TarInfo('pending/' + path.stem + '/' + ciphertext_hash)
                                    member.size, member.mode = size_bytes, 0o600
                                    reader = _DigestReader(source)
                                    archive.addfile(member, reader)
                                    archive.members.clear()
                                    require(reader.digest.hexdigest() == ciphertext_hash
                                            and os.fstat(source.fileno()).st_size == size_bytes,
                                            ReasonCode.HASH_MISMATCH)
                        files_encrypt.stdin.close()
                        if files_encrypt.wait():
                            return self._error(context, ReasonCode.SOURCE_NOT_APPROVED)
                        output.flush()
                        os.fsync(output.fileno())
                    with files_partial.open('rb') as source:
                        manifest['files_archive'] = {'sha256': hashlib.file_digest(source, 'sha256').hexdigest(),
                                                     'size_bytes': files_partial.stat().st_size}
                    os.lseek(key_fd, 0, os.SEEK_SET)
                if cadence is not None:
                    manifest['retention'] = {'cadence': cadence, 'created_at': started_at.isoformat()}
                header = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode('ascii')
                if len(header) > CHUNK - (4096 if self.full_inventory else 0):
                    return self._error(context, ReasonCode.LIMIT_EXCEEDED)
                output = stack.enter_context(os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb'))
                encrypt = subprocess.Popen([self.age, '--encrypt', '--recipients-file', f'/proc/self/fd/{key_fd}'],
                    stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL, pass_fds=(key_fd,))
                processes.append(encrypt)
                dump = subprocess.Popen([self.pg_dump, '--format=custom', '--no-owner', '--no-acl',
                                         '--snapshot', snapshot], env=self.pg_env,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                processes.append(dump)
                encrypt.stdin.write(MAGIC + struct.pack('!I', len(header)) + header)
                shutil.copyfileobj(dump.stdout, encrypt.stdin, CHUNK)
                dump.stdout.close()
                encrypt.stdin.close()
                # Both exit codes matter: an authenticated age file can contain a failed dump.
                dump_status, age_status = dump.wait(), encrypt.wait()
                if dump_status or age_status:
                    return self._error(context, ReasonCode.SOURCE_NOT_APPROVED)
                output.flush()
                os.fsync(output.fileno())
            with partial.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            size = partial.stat().st_size
            if self.private_root is not None:
                files_partial.rename(files_final)
            partial.rename(final)
            self._persist(object_id + '.json', {'object_ref': 'backup/' + object_id,
                'version': version, 'ciphertext_hash': digest, 'size_bytes': size, 'state': 'verified',
                **({'retention': {**manifest['retention'], 'files_hash': manifest['files_archive']['sha256'],
                    'files_size': manifest['files_archive']['size_bytes']},
                    'environment': context.environment.value, 'domain': context.domain}
                   if cadence is not None else {}),
                **({'recovery_manifest': manifest, 'completed_at': self.clock().isoformat()}
                   if self.full_inventory else {})})
            return StoredObject(schema_version=StoredObject.SCHEMA, object_ref='backup/' + object_id,
                version=version, ciphertext_hash=digest, size_bytes=size, state='verified')
        except (OSError, ValueError, psycopg2.Error):
            return self._error(context, ReasonCode.SOURCE_NOT_APPROVED)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                process.wait()
                for stream in (process.stdin, process.stdout):
                    if stream and not stream.closed:
                        with suppress(BrokenPipeError):
                            stream.close()
            partial.unlink(missing_ok=True)
            files_partial.unlink(missing_ok=True)
            # A publication failure leaves no valid registration.
            if not (self.directory / (object_id + '.json')).exists():
                final.unlink(missing_ok=True)
                files_final.unlink(missing_ok=True)

    def _pending_files(self, connection):
        with connection.cursor() as cursor:
            cursor.execute(FILES_QUERY)
            live = {row[0]: row[1:] for row in cursor.fetchmany(self.limits.max_actions + 1)}
        require(len(live) <= self.limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
        pending, seen, scanned = [], set(), 0
        for path in self.private_root.iterdir():
            scanned += 1
            require(scanned <= self.limits.max_actions * 3 + 1, ReasonCode.LIMIT_EXCEEDED)
            if path.name == '.restore-state.json' or re.fullmatch(r'operation-[0-9a-f]{64}\.lock', path.name):
                continue
            require(re.fullmatch(r'[0-9a-f]{64}\.sealed', path.name), ReasonCode.SOURCE_NOT_APPROVED)
            object_ref = 'private/' + path.stem
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
                info = os.fstat(source.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                        and not info.st_mode & 0o077, ReasonCode.SOURCE_NOT_APPROVED)
                measured = (hashlib.file_digest(source, 'sha256').hexdigest(), info.st_size)
            if object_ref in live:
                require(measured == live[object_ref], ReasonCode.HASH_MISMATCH)
                seen.add(object_ref)
            else:
                pending.append((object_ref, *measured))
        require(seen == set(live), ReasonCode.SOURCE_NOT_APPROVED)
        return tuple(sorted(pending))

    def source_inventory(self, context):
        """Read the complete source identity; no rows or filenames leave this adapter."""
        if not self.full_inventory or not self._allowed(context):
            return self._error(context, ReasonCode.AUTHORIZATION_DENIED)
        try:
            with closing(psycopg2.connect(**self.database)) as connection:
                connection.set_session(isolation_level='REPEATABLE READ', readonly=True)
                return {'schema': _measure(connection, _schema_checks(connection)),
                        'private_files': _measure(connection, (('files', FILES_QUERY),))['files'],
                        'pending_files': _file_measure(self._pending_files(connection))}
        except ContractViolation as error:
            return self._error(context, error.code)
        except (OSError, ValueError, psycopg2.Error):
            return self._error(context, ReasonCode.SOURCE_NOT_APPROVED)

    def _registration(self, object_id):
        with os.fdopen(os.open(self.directory / (object_id + '.json'),
                              os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and not info.st_mode & 0o077, ReasonCode.SOURCE_NOT_APPROVED)
            encoded = source.read(CHUNK + 1)
        require(len(encoded) <= CHUNK, ReasonCode.LIMIT_EXCEEDED)
        metadata = json.loads(encoded)
        require(type(metadata) is dict, ReasonCode.INVALID_VALUE)
        return metadata

    def retention_inventory(self, context, limits, *, full_only=False):
        """Bounded, verified local registrations only; unknown/legacy files are never adopted."""
        if self.identity_ref is not None or self.private_root is None or not self._allowed(context):
            return self._error(context, ReasonCode.AUTHORIZATION_DENIED)
        try:
            records = []
            scanned = 0
            for path in self.directory.iterdir():
                if not re.fullmatch(r'[0-9a-f]{32}\.json', path.name):
                    continue
                scanned += 1
                require(scanned <= limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
                metadata = self._registration(path.stem)
                if 'retention' not in metadata:
                    continue
                if full_only and 'full_inventory' not in metadata.get('recovery_manifest', {}):
                    continue
                require(metadata.get('environment') == context.environment.value
                        and metadata.get('domain') == context.domain, ReasonCode.SOURCE_NOT_APPROVED)
                require(metadata.get('object_ref') == 'backup/' + path.stem,
                        ReasonCode.REPORT_MISMATCH)
                if metadata.get('state') == 'retired':
                    continue
                require(metadata.get('state') == 'verified', ReasonCode.DELIVERY_UNKNOWN)
                retention = metadata['retention']
                require(type(retention) is dict and set(retention) == {
                    'cadence', 'created_at', 'files_hash', 'files_size'}, ReasonCode.INVALID_VALUE)
                record = BackupRetentionRecord(schema_version=BackupRetentionRecord.SCHEMA,
                    backup=StoredObject(schema_version=StoredObject.SCHEMA,
                        **{name: metadata[name] for name in (
                            'object_ref', 'version', 'ciphertext_hash', 'size_bytes', 'state')}),
                    created_at=datetime.fromisoformat(retention['created_at']),
                    cadence=retention['cadence'], files_hash=retention['files_hash'],
                    files_size=retention['files_size'])
                # Check the retained set too: a corrupt newer bundle cannot evict an older one.
                for suffix, expected_hash, expected_size in (
                        ('.age', record.backup.ciphertext_hash, record.backup.size_bytes),
                        ('.files.age', record.files_hash, record.files_size)):
                    with os.fdopen(os.open(self.directory / (path.stem + suffix),
                                          os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
                        info = os.fstat(source.fileno())
                        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                                and not info.st_mode & 0o077, ReasonCode.SOURCE_NOT_APPROVED)
                        require(info.st_size == expected_size and
                                hashlib.file_digest(source, 'sha256').hexdigest() == expected_hash,
                                ReasonCode.HASH_MISMATCH)
                records.append(record)
            return tuple(records)
        except ContractViolation as error:
            code = error.code
        except (OSError, ValueError, TypeError, KeyError):
            code = ReasonCode.SOURCE_NOT_APPROVED
        return self._error(context, code)

    def key_inventory(self, context, limits):
        """Local retained-bundle references, never authority to destroy a key or identity."""
        if not self._allowed(context):
            return self._error(context, ReasonCode.AUTHORIZATION_DENIED)
        try:
            bundles, unresolved, keys, recipients = [], 0, set(), set()
            ids = {path.name.split('.')[0] for path in self.directory.iterdir()
                   if re.fullmatch(r'[0-9a-f]{32}\.(?:json|age|files\.age)', path.name)}
            require(len(ids) <= limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
            for object_id in sorted(ids):
                if not (self.directory / (object_id + '.json')).exists():
                    unresolved += 1  # Opaque/orphan packages remain retained, not adopted or deleted.
                    continue
                metadata = self._registration(object_id)
                require(metadata.get('object_ref') == 'backup/' + object_id, ReasonCode.REPORT_MISMATCH)
                if metadata.get('state') == 'retired':
                    require(not any((self.directory / (object_id + suffix)).exists()
                        for suffix in ('.age', '.files.age')), ReasonCode.DELIVERY_UNKNOWN)
                    continue
                require(metadata.get('state') == 'verified', ReasonCode.DELIVERY_UNKNOWN)
                manifest = metadata.get('recovery_manifest')
                if not manifest:
                    unresolved += 1  # Older registrations do not record all required references.
                    continue
                require(manifest['environment'] == context.environment.value and manifest['domain'] == context.domain,
                        ReasonCode.SOURCE_NOT_APPROVED)
                for suffix, expected_hash, expected_size in (
                        ('.age', metadata['ciphertext_hash'], metadata['size_bytes']),
                        ('.files.age', manifest['files_archive']['sha256'], manifest['files_archive']['size_bytes'])):
                    with os.fdopen(os.open(self.directory / (object_id + suffix), os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
                        info = os.fstat(source.fileno())
                        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077
                                and info.st_size == expected_size and hashlib.file_digest(source, 'sha256').hexdigest()
                                == expected_hash, ReasonCode.HASH_MISMATCH)
                references = tuple(KeyReference.from_wire(value) for value in manifest['required_keys'])
                recipient = KeyReference.from_wire(manifest['full_inventory']['recipient'])
                require(recipient.key_ref == manifest['recipient_ref'] and recipient.purpose is KeyPurpose.BACKUP_PUBLIC,
                        ReasonCode.REPORT_MISMATCH)
                refs = sorted({ref.key_ref for ref in references})
                keys.update(refs)
                recipients.add(recipient.key_ref)
                bundles.append({'backup_ref': metadata['object_ref'], 'recipient_ref': recipient.key_ref,
                    'required_key_refs': refs})
            return {'scope': 'local-retained-backups', 'bundles': bundles, 'required_key_refs': sorted(keys),
                'recipient_refs': sorted(recipients), 'unresolved_bundles': unresolved,
                'metadata_age_authenticated': False, 'retirement_allowed': False,
                'offline_identity_mapping_required': True}
        except ContractViolation as error:
            code = error.code
        except (OSError, KeyError, TypeError, ValueError):
            code = ReasonCode.SOURCE_NOT_APPROVED
        return self._error(context, code)

    def retire(self, record, context):
        """M4 supplies an approved inventory entry; retain intent/receipt, never unlink by glob."""
        if self.identity_ref is not None or self.private_root is None or not self._allowed(context):
            return self._error(context, ReasonCode.AUTHORIZATION_DENIED)
        try:
            require(re.fullmatch(r'backup/[0-9a-f]{32}', record.backup.object_ref),
                    ReasonCode.INVALID_VALUE)
            object_id = record.backup.object_ref.split('/')[1]
            metadata = self._registration(object_id)
            expected = {name: getattr(record.backup, name) for name in (
                'object_ref', 'version', 'ciphertext_hash', 'size_bytes', 'state')}
            expected.update(environment=context.environment.value, domain=context.domain,
                retention=dict(created_at=record.created_at.isoformat(), cadence=record.cadence,
                               files_hash=record.files_hash, files_size=record.files_size))
            compared = {name: value for name, value in metadata.items()
                        if name not in ('recovery_manifest', 'completed_at')}
            require(compared == expected, ReasonCode.REPORT_MISMATCH)
            event_id = 'backup-retire/' + object_id
            metadata.update(state='retiring', event_id=event_id)
            self._persist(object_id + '.json', metadata)
            (self.directory / (object_id + '.age')).unlink()
            (self.directory / (object_id + '.files.age')).unlink()
            now = self.clock()
            metadata.update(state='retired', retired_at=now.isoformat())
            self._persist(object_id + '.json', metadata)
            return AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=event_id,
                durability=Durability.DURABLE, stored_at=now, chain_version=None,
                entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
        except ContractViolation as error:
            return self._error(context, error.code)
        except (OSError, ValueError, TypeError, KeyError):
            return self._error(context, ReasonCode.DELIVERY_UNKNOWN)

    def restore(self, backup, context):
        if self.identity_ref is None or not self._allowed(context):
            return self._error(context, ReasonCode.AUTHORIZATION_DENIED)
        if not re.fullmatch(r'backup/[0-9a-f]{32}', backup.object_ref) or backup.state != 'verified':
            return self._error(context, ReasonCode.INVALID_VALUE)
        material = self.resolver.resolve(self.identity_ref, KeyPurpose.BACKUP_PRIVATE, self.service_identity)
        if isinstance(material, ProtectionError):
            return material
        object_id = backup.object_ref.split('/')[1]
        processes = []
        try:
            with ExitStack() as stack:
                encrypted = stack.enter_context((self.directory / (object_id + '.age')).open('rb'))
                if (os.fstat(encrypted.fileno()).st_size != backup.size_bytes
                        or hashlib.file_digest(encrypted, 'sha256').hexdigest() != backup.ciphertext_hash):
                    return self._error(context, ReasonCode.HASH_MISMATCH)
                key_fd = os.memfd_create('backup-identity', os.MFD_CLOEXEC)
                stack.callback(os.close, key_fd)
                identity = bytes(material.borrow(KeyPurpose.BACKUP_PRIVATE)).strip()
                if not re.fullmatch(rb'AGE-SECRET-KEY-1[0-9A-Z]{58}', identity):
                    return self._error(context, ReasonCode.KEY_UNAVAILABLE)
                os.write(key_fd, identity + b'\n')
                # Authenticate the entire age stream BEFORE sending any SQL/archive to a DB.
                encrypted.seek(0)
                os.lseek(key_fd, 0, os.SEEK_SET)
                command = [self.age, '--decrypt', '--identity', f'/proc/self/fd/{key_fd}']
                checked = subprocess.run(command, stdin=encrypted, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, pass_fds=(key_fd,))
                if checked.returncode:
                    return self._error(context, ReasonCode.CIPHERTEXT_INVALID)
                connection = stack.enter_context(closing(psycopg2.connect(**self.database)))
                with connection.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                                   "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'")
                    if cursor.fetchone()[0]:
                        return self._error(context, ReasonCode.SOURCE_NOT_APPROVED)
                connection.rollback()
                encrypted.seek(0)
                os.lseek(key_fd, 0, os.SEEK_SET)
                decrypt = subprocess.Popen(command, stdin=encrypted, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, pass_fds=(key_fd,))
                processes.append(decrypt)
                if decrypt.stdout.read(len(MAGIC)) != MAGIC:
                    return self._error(context, ReasonCode.UNSUPPORTED_FORMAT)
                length = struct.unpack('!I', decrypt.stdout.read(4))[0]
                if length > CHUNK:
                    return self._error(context, ReasonCode.LIMIT_EXCEEDED)
                manifest = json.loads(decrypt.stdout.read(length))
                expected_format = 'ds.pg-age.v2' if self.private_root is not None else 'ds.pg-age.v1'
                if (type(manifest) is not dict or manifest.get('format') != expected_format
                        or manifest.get('environment') != context.environment.value
                        or manifest.get('domain') != context.domain
                        or type(manifest.get('checks')) is not dict
                        or set(manifest['checks']) != {name for name, _ in self.checks}):
                    return self._error(context, ReasonCode.SOURCE_NOT_APPROVED)
                files_actual = None
                if self.private_root is not None:
                    entries = tuple(self.private_root.iterdir())
                    if (manifest.get('code_version') != self.code_version
                            or manifest.get('required_keys') != [key.to_wire() for key in self.required_keys]
                            or bool(manifest.get('full_inventory')) != self.full_inventory
                            or (entries != (self.private_root / '.restore-state.json',)
                                if self.full_inventory else bool(entries))):
                        return self._error(context, ReasonCode.SOURCE_NOT_APPROVED)
                    if self.full_inventory:
                        require(type(manifest['full_inventory']) is dict and
                                set(manifest['full_inventory']) == {'snapshot_at', 'recipient', 'source_identity',
                                                                   'schema', 'pending_files'},
                                ReasonCode.INVALID_VALUE)
                        datetime.fromisoformat(manifest['full_inventory']['snapshot_at'])
                        KeyReference.from_wire(manifest['full_inventory']['recipient'])
                    for key in self.required_keys:
                        available = self.resolver.resolve(key, key.purpose, self.service_identity)
                        if isinstance(available, ProtectionError):
                            return available
                    file_meta = manifest['files_archive']
                    if (type(file_meta) is not dict or type(file_meta.get('size_bytes')) is not int
                            or file_meta['size_bytes'] <= 0 or type(file_meta.get('sha256')) is not str
                            or not re.fullmatch(r'[0-9a-f]{64}', file_meta['sha256'])
                            or type(manifest.get('private_files')) is not dict):
                        return self._error(context, ReasonCode.INVALID_VALUE)
                    files_source = stack.enter_context((self.directory / (object_id + '.files.age')).open('rb'))
                    if (os.fstat(files_source.fileno()).st_size != file_meta['size_bytes']
                            or hashlib.file_digest(files_source, 'sha256').hexdigest() != file_meta['sha256']):
                        return self._error(context, ReasonCode.HASH_MISMATCH)
                    files_source.seek(0)
                    os.lseek(key_fd, 0, os.SEEK_SET)
                    checked = subprocess.run(command, stdin=files_source, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, pass_fds=(key_fd,))
                    if checked.returncode:
                        return self._error(context, ReasonCode.CIPHERTEXT_INVALID)
                    files_source.seek(0)
                    os.lseek(key_fd, 0, os.SEEK_SET)
                    files_decrypt = subprocess.Popen(command, stdin=files_source, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, pass_fds=(key_fd,))
                    processes.append(files_decrypt)
                    file_digest, file_count = hashlib.sha256(), 0
                    pending_digest, pending_count = hashlib.sha256(), 0
                    with tarfile.open(fileobj=files_decrypt.stdout, mode='r|') as archive:
                        for member in archive:
                            match = re.fullmatch(r'(private|pending)/([0-9a-f]{64})/([0-9a-f]{64})', member.name)
                            if (not match or not member.isfile() or member.size < 0
                                    or (match[1] == 'pending' and not self.full_inventory)):
                                return self._error(context, ReasonCode.CIPHERTEXT_INVALID)
                            path = self.private_root / (match[2] + '.sealed')
                            with archive.extractfile(member) as source, os.fdopen(os.open(path,
                                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as target:
                                reader = _DigestReader(source)
                                shutil.copyfileobj(reader, target, CHUNK)
                                target.flush()
                                os.fsync(target.fileno())
                                if reader.digest.hexdigest() != match[3]:
                                    return self._error(context, ReasonCode.HASH_MISMATCH)
                            encoded = json.dumps(('private/' + match[2], match[3], member.size),
                                                 separators=(',', ':')).encode('ascii')
                            measured = pending_digest if match[1] == 'pending' else file_digest
                            measured.update(struct.pack('!Q', len(encoded)))
                            measured.update(encoded)
                            if match[1] == 'pending':
                                pending_count += 1
                            else:
                                file_count += 1
                            archive.members.clear()
                    # Drain authenticated tar padding without keeping the archive in memory.
                    while files_decrypt.stdout.read(CHUNK):
                        pass
                    files_decrypt.stdout.close()
                    if files_decrypt.wait():
                        return self._error(context, ReasonCode.CIPHERTEXT_INVALID)
                    files_actual = {'records': file_count, 'sha256': file_digest.hexdigest()}
                    if files_actual != manifest['private_files']:
                        return self._error(context, ReasonCode.REPORT_MISMATCH)
                    if self.full_inventory:
                        require({'records': pending_count, 'sha256': pending_digest.hexdigest()} ==
                                manifest['full_inventory']['pending_files'], ReasonCode.REPORT_MISMATCH)
                    directory = os.open(self.private_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                restore = subprocess.Popen([self.pg_restore, '--single-transaction', '--exit-on-error',
                    '--no-owner', '--no-acl', '--dbname', self.database['dbname']], env=self.pg_env,
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processes.append(restore)
                shutil.copyfileobj(decrypt.stdout, restore.stdin, CHUNK)
                decrypt.stdout.close()
                restore.stdin.close()
                restore_status, age_status = restore.wait(), decrypt.wait()
                if restore_status or age_status:
                    return self._error(context, ReasonCode.CIPHERTEXT_INVALID)
                connection.set_session(isolation_level='REPEATABLE READ', readonly=True)
                actual = _measure(connection, self.checks)
                if actual != manifest['checks']:
                    return self._error(context, ReasonCode.REPORT_MISMATCH)
                if self.private_root is not None and _measure(connection, (('files', FILES_QUERY),))['files'] != files_actual:
                    return self._error(context, ReasonCode.REPORT_MISMATCH)
                if self.full_inventory:
                    require(_measure(connection, _schema_checks(connection)) == manifest['full_inventory']['schema']
                            and _file_measure(self._pending_files(connection)) == manifest['full_inventory']['pending_files'],
                            ReasonCode.REPORT_MISMATCH)
                now = self.clock()
                event_id = 'backup-restore/' + uuid4().hex
                self._persist(event_id.replace('/', '-') + '.json', {
                    'event_id': event_id, 'stored_at': now.isoformat(), 'backup_ref': backup.object_ref,
                    'ciphertext_hash': backup.ciphertext_hash, 'durability': 'durable',
                    'consistency_point': manifest['consistency_point'], 'checks': actual,
                    **({'format': 'ds.pg-age.v2', 'code_version': self.code_version, 'private_files': files_actual,
                        'required_keys': manifest['required_keys']} if self.private_root is not None else {}),
                    **({'full_inventory': manifest['full_inventory'], 'target_identity': self.source_identity}
                       if self.full_inventory else {})})
                return AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=event_id,
                    durability=Durability.DURABLE, stored_at=now, chain_version=None,
                    entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
        except (OSError, ValueError, KeyError, struct.error, tarfile.TarError, psycopg2.Error):
            return self._error(context, ReasonCode.CIPHERTEXT_INVALID)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                process.wait()
                for stream in (process.stdin, process.stdout):
                    if stream and not stream.closed:
                        with suppress(BrokenPipeError):
                            stream.close()

    def read_restoration(self, receipt, context):
        if not self.full_inventory or not self._allowed(context):
            return self._error(context, ReasonCode.AUTHORIZATION_DENIED)
        try:
            require(type(receipt) is AuditReceipt and receipt.durability is Durability.DURABLE
                    and receipt.chain_version is None
                    and re.fullmatch(r'backup-restore/[0-9a-f]{32}', receipt.event_id), ReasonCode.INVALID_VALUE)
            record = self._registration(receipt.event_id.replace('/', '-'))
            require(record.get('event_id') == receipt.event_id and record.get('stored_at') == receipt.stored_at.isoformat()
                    and record.get('format') == 'ds.pg-age.v2' and record.get('code_version') == self.code_version
                    and record.get('target_identity') == self.source_identity and bool(record.get('full_inventory')),
                    ReasonCode.REPORT_MISMATCH)
            return record
        except ContractViolation as error:
            return self._error(context, error.code)
        except (OSError, ValueError, TypeError, KeyError):
            return self._error(context, ReasonCode.SOURCE_NOT_APPROVED)

    def _persist(self, name, metadata):
        """Only non-secret success metadata; fsync file and rename before dir fsync."""
        temporary = self.directory / (name + '.partial')
        try:
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
                json.dump(metadata, output, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            temporary.rename(self.directory / name)
            descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)
