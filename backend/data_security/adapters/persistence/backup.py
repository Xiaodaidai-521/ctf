"""M6 PostgreSQL/age adapter. B supplies connections, references and service identity.

Online instances have only a recipient resolver. Offline restore is a separate
instance with a separately authorized identity reference. No secret file lookup,
SQL staging file, shell pipeline, SDK crypto, or unbounded backup read occurs here.
The encrypted header is a recovery manifest; this is database-only (phase 3).
"""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
from contextlib import ExitStack, closing, suppress
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg2

from data_security.contracts.crypto import KeyReference
from data_security.contracts.enums import Durability, KeyPurpose, Purpose, ReasonCode, Role
from data_security.contracts.events import AuditReceipt, ProtectionError
from data_security.contracts.ports import KeyResolverPort, StoredObject
from data_security.contracts.schema import reference


CHUNK = 64 * 1024
MAGIC = b'DS-PG-AGE-1\n'


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
                 identity_ref: KeyReference | None = None):
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
        self.checks = checks
        self.environment = environment
        self.domain = domain
        self.age, self.pg_dump, self.pg_restore = map(str, (age, pg_dump, pg_restore))
        self.identity_ref = identity_ref
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

    def create(self, snapshot_ref, recipient, context):
        reference(snapshot_ref)
        if self.identity_ref is not None or not self._allowed(context):
            return self._error(context, ReasonCode.AUTHORIZATION_DENIED)
        material = self.resolver.resolve(recipient, KeyPurpose.BACKUP_PUBLIC, self.service_identity)
        if isinstance(material, ProtectionError):
            return material
        object_id = uuid4().hex
        partial = self.directory / (object_id + '.partial')
        final = self.directory / (object_id + '.age')
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
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_export_snapshot(), txid_current_snapshot()::text')
                    snapshot, consistency = cursor.fetchone()
                manifest = {'format': 'ds.pg-age.v1', 'snapshot_ref': snapshot_ref,
                            'consistency_point': consistency, 'snapshot_id': snapshot,
                            'environment': context.environment.value, 'domain': context.domain,
                            'recipient_ref': recipient.key_ref, 'checks': _measure(connection, self.checks)}
                header = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode('ascii')
                if len(header) > CHUNK:
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
            partial.rename(final)
            self._persist(object_id + '.json', {'object_ref': 'backup/' + object_id,
                'version': 'v1', 'ciphertext_hash': digest, 'size_bytes': size, 'state': 'verified'})
            return StoredObject(schema_version=StoredObject.SCHEMA, object_ref='backup/' + object_id,
                version='v1', ciphertext_hash=digest, size_bytes=size, state='verified')
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
            # A publication failure leaves no valid registration.
            if not (self.directory / (object_id + '.json')).exists():
                final.unlink(missing_ok=True)

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
                if (type(manifest) is not dict or manifest.get('format') != 'ds.pg-age.v1'
                        or manifest.get('environment') != context.environment.value
                        or manifest.get('domain') != context.domain
                        or type(manifest.get('checks')) is not dict
                        or set(manifest['checks']) != {name for name, _ in self.checks}):
                    return self._error(context, ReasonCode.SOURCE_NOT_APPROVED)
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
                now = datetime.now(timezone.utc)
                event_id = 'backup-restore/' + uuid4().hex
                self._persist(event_id.replace('/', '-') + '.json', {
                    'event_id': event_id, 'stored_at': now.isoformat(), 'backup_ref': backup.object_ref,
                    'ciphertext_hash': backup.ciphertext_hash, 'durability': 'durable',
                    'consistency_point': manifest['consistency_point'], 'checks': actual})
                return AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=event_id,
                    durability=Durability.DURABLE, stored_at=now, chain_version=None,
                    entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
        except (OSError, ValueError, KeyError, struct.error, psycopg2.Error):
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
