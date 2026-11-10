"""Private immutable ciphertext files, with same-database publication state.

File creation is durable before its candidate row is inserted. A rollback can
leave an orphan ciphertext file; it never makes that file readable via this port.
"""
import hashlib
import os
from pathlib import Path
import re
import stat

from django.db import DatabaseError, transaction

from data_security.contracts import (
    CipherEnvelope, ContractViolation, Environment, ProtectionError, ReasonCode, StoredObject, content_hash,
)
from data_security.contracts.schema import MAX_WIRE_BYTES, canonical_bytes, require
from data_security.adapters.persistence.models import PrivateObject


class DjangoPrivateStore:
    def __init__(self, *, root, crypto, environment):
        require(type(environment) is Environment and environment is not Environment.PRODUCTION,
                ReasonCode.SOURCE_NOT_APPROVED)
        root = Path(root)
        require(root.is_absolute() and root == root.resolve(), ReasonCode.AUTHORIZATION_DENIED)
        info = root.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
                ReasonCode.AUTHORIZATION_DENIED)
        self.root, self.crypto, self.environment = root, crypto, environment

    def write_candidate(self, envelope, context):
        return self._run('write', context, envelope=envelope)

    def verify(self, candidate, context):
        return self._run('verify', context, stored=candidate)

    def publish(self, candidate, context):
        return self._run('publish', context, stored=candidate)

    def read(self, stored, context):
        """Return ciphertext only; the download use case must fully open it before sending."""
        return self._run('read', context, stored=stored)

    def open_verified_source(self, stored, context):
        """Internal source capability; its owner must authenticate current access and the reference."""
        return self._run('open_source', context, stored=stored)

    def read_verified_ciphertext(self, stored, context):
        """B3 staging input only; the maintenance owner must fully authenticate before resealing."""
        return self._run('read_verified', context, stored=stored)

    def inspect_recovery(self, stored, context):
        """Read an already registered object without adopting, verifying or publishing it."""
        return self._run('inspect_recovery', context, stored=stored)

    def read_prepared(self, context):
        """Observe one retained preparation; absence or ambiguity is not zero effects."""
        try:
            require(context.environment is self.environment, ReasonCode.SOURCE_NOT_APPROVED)
            identity = content_hash(dict(project=context.project_ref, environment=context.environment,
                object_uuid=context.object_uuid, version=context.object_version, field=context.field_ref))
            rows = list(PrivateObject.objects.filter(context_hash=identity)[:2])
            require(len(rows) == 1 and rows[0].state == 'verified', ReasonCode.DELIVERY_UNKNOWN)
            return self.verify(self._stored(rows[0]), context)
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='private-store/prepared')

    def recover_candidate(self, stored, context):
        """Recover registration from an exact pre-write intention, never a guessed path."""
        try:
            require(context.environment is self.environment, ReasonCode.SOURCE_NOT_APPROVED)
            identity = content_hash(dict(project=context.project_ref, environment=context.environment,
                object_uuid=context.object_uuid, version=context.object_version, field=context.field_ref))
            require(stored.object_ref == 'private/' + content_hash({
                'context': identity, 'ciphertext': stored.ciphertext_hash}) and
                stored.version == context.object_version, ReasonCode.HASH_MISMATCH)
            envelope = self._read_file(stored.object_ref, stored.size_bytes, stored.ciphertext_hash)
            opened = self.crypto.open(envelope, context, envelope.key)
            if isinstance(opened, ProtectionError):
                return opened
            with transaction.atomic():
                record, _ = PrivateObject.objects.select_for_update().get_or_create(
                    object_ref=stored.object_ref, defaults={'version': stored.version, 'context_hash': identity,
                        'ciphertext_hash': stored.ciphertext_hash, 'size_bytes': stored.size_bytes})
                require((record.context_hash, record.version, record.ciphertext_hash, record.size_bytes) ==
                        (identity, stored.version, stored.ciphertext_hash, stored.size_bytes) and
                        record.state in ('candidate', 'verified'), ReasonCode.AUTHORIZATION_DENIED)
                if record.state == 'candidate':
                    record.state = 'verified'
                    record.save(update_fields=['state'])
                return self._stored(record)
        except ContractViolation as error:
            code = error.code
        except (OSError, DatabaseError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='private-store/recover')

    def retire_candidate(self, stored, context):
        """Delete only an explicitly fenced intention; never a published export or arbitrary orphan."""
        try:
            require(context.environment is self.environment, ReasonCode.SOURCE_NOT_APPROVED)
            identity = content_hash(dict(project=context.project_ref, environment=context.environment,
                object_uuid=context.object_uuid, version=context.object_version, field=context.field_ref))
            require(stored.object_ref == 'private/' + content_hash({
                'context': identity, 'ciphertext': stored.ciphertext_hash}) and
                stored.version == context.object_version, ReasonCode.HASH_MISMATCH)
            with transaction.atomic():
                record = PrivateObject.objects.select_for_update().filter(object_ref=stored.object_ref).first()
                if record is not None:
                    require((record.context_hash, record.version, record.ciphertext_hash, record.size_bytes) ==
                            (identity, stored.version, stored.ciphertext_hash, stored.size_bytes) and
                            record.state in ('candidate', 'verified', 'retired'), ReasonCode.AUTHORIZATION_DENIED)
                    record.state = 'retired'
                    record.save(update_fields=['state'])
            path = self.root / (stored.object_ref.removeprefix('private/') + '.sealed')
            try:
                info = path.lstat()
            except FileNotFoundError:
                info = None
            if info is not None:
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                        not info.st_mode & 0o077 and info.st_nlink == 1, ReasonCode.AUTHORIZATION_DENIED)
                path.unlink()
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return True
        except ContractViolation as error:
            code = error.code
        except (OSError, DatabaseError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='private-store/cleanup')

    def _read_file(self, object_ref, size_bytes, ciphertext_hash):
        path = self.root / (object_ref.removeprefix('private/') + '.sealed')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                    not info.st_mode & 0o077 and info.st_nlink == 1, ReasonCode.AUTHORIZATION_DENIED)
            require(info.st_size == size_bytes and info.st_size <= MAX_WIRE_BYTES,
                    ReasonCode.CIPHERTEXT_INVALID)
            encoded = source.read(MAX_WIRE_BYTES + 1)
        require(len(encoded) == size_bytes and hashlib.sha256(encoded).hexdigest() == ciphertext_hash,
                ReasonCode.HASH_MISMATCH)
        return CipherEnvelope.from_json(encoded)

    def _stored(self, record):
        return StoredObject(schema_version=StoredObject.SCHEMA, object_ref=record.object_ref,
            version=record.version, ciphertext_hash=record.ciphertext_hash,
            size_bytes=record.size_bytes, state=record.state)

    def _run(self, operation, context, *, envelope=None, stored=None):
        try:
            require(context.environment is self.environment, ReasonCode.SOURCE_NOT_APPROVED)
            # A renewed download grant is not a new ciphertext identity.
            context_hash = content_hash(dict(project=context.project_ref, environment=context.environment,
                object_uuid=context.object_uuid, version=context.object_version, field=context.field_ref))
            if operation == 'write':
                require(type(envelope) is CipherEnvelope, ReasonCode.INVALID_TYPE)
                encoded = canonical_bytes(envelope)
                require(len(encoded) <= MAX_WIRE_BYTES, ReasonCode.LIMIT_EXCEEDED)
                ciphertext_hash = hashlib.sha256(encoded).hexdigest()
                object_ref = 'private/' + content_hash({'context': context_hash, 'ciphertext': ciphertext_hash})
                path = self.root / (object_ref.removeprefix('private/') + '.sealed')
                try:
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                except FileExistsError:
                    # Reuse only a complete, identical immutable file; never overwrite a partial orphan.
                    self._read_file(object_ref, len(encoded), ciphertext_hash)
                else:
                    with os.fdopen(fd, 'wb') as target:
                        target.write(encoded)
                        target.flush()
                        os.fsync(target.fileno())
                directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
                record, _ = PrivateObject.objects.get_or_create(object_ref=object_ref, defaults={
                    'version': context.object_version, 'context_hash': context_hash,
                    'ciphertext_hash': ciphertext_hash, 'size_bytes': len(encoded)})
                return self._stored(record)

            require(type(stored) is StoredObject and
                    re.fullmatch(r'private/[0-9a-f]{64}', stored.object_ref) is not None,
                    ReasonCode.AUTHORIZATION_DENIED)
            # Fetching publication state and checking identity occur in one short transaction.
            with transaction.atomic():
                rows = PrivateObject.objects.select_for_update() if operation == 'publish' else PrivateObject.objects
                record = rows.get(object_ref=stored.object_ref)
                require(record.state in ('candidate', 'verified', 'published') or
                        (operation == 'inspect_recovery' and record.state == 'retired'), ReasonCode.AUTHORIZATION_DENIED)
                require((record.context_hash, record.version, record.ciphertext_hash, record.size_bytes) ==
                        (context_hash, stored.version, stored.ciphertext_hash, stored.size_bytes),
                        ReasonCode.HASH_MISMATCH)
                if operation == 'inspect_recovery' and record.state == 'retired':
                    return None  # Retained identity only; retired bytes need not still exist.
                if operation == 'publish':
                    require(record.state in ('verified', 'published'), ReasonCode.AUTHORIZATION_DENIED)
                    if record.state == 'verified':
                        record.state = 'published'
                        record.save(update_fields=['state'])
                    return self._stored(record)
                if operation == 'read':
                    require(record.state == 'published', ReasonCode.AUTHORIZATION_DENIED)
                if operation in ('open_source', 'read_verified'):
                    require(record.state == stored.state == 'verified', ReasonCode.AUTHORIZATION_DENIED)
            envelope = self._read_file(record.object_ref, record.size_bytes, record.ciphertext_hash)
            if operation in ('read', 'read_verified', 'inspect_recovery'):
                return envelope
            # GCM authentication and bounded payload validation happen before the verified state.
            opened = self.crypto.open(envelope, context, envelope.key)
            if isinstance(opened, ProtectionError):
                return opened
            if operation == 'open_source':
                return opened
            with transaction.atomic():
                record = PrivateObject.objects.select_for_update().get(pk=record.pk)
                if record.state == 'candidate':
                    record.state = 'verified'
                    record.save(update_fields=['state'])
                return self._stored(record)
        except ContractViolation as error:
            code = error.code
        except PrivateObject.DoesNotExist:
            code = ReasonCode.AUTHORIZATION_DENIED
        except (OSError, DatabaseError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='private-store/operation')
