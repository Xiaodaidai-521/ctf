"""Upload intentions and explicit cleanup, with no database lock across file I/O.

The local file gate fences a live preparer from reconciliation and deletion. It
is released by the OS on process exit; expiry or a missing row is not that proof.
Lock files contain no payload and are retained so waiters cannot split the gate.
"""
from contextlib import contextmanager
from dataclasses import replace
import fcntl
import hashlib
import os
import stat

from django.db import connection, transaction

from data_security.contracts import (
    Environment, FileUploadOperation, ObjectContext, ProtectionError, ReasonCode, StoredObject, content_hash,
)
from data_security.contracts.schema import canonical_bytes, reference, require
from data_security.adapters.persistence.models import PrivateFileOperation


class DjangoFileOperations:
    def __init__(self, *, store):
        self.store = store

    def _snapshot(self, row):
        return FileUploadOperation(schema_version=FileUploadOperation.SCHEMA,
            operation_ref=row.operation_ref, actor_ref=row.actor_ref, scope_ref=row.scope_ref,
            request_hash=row.request_hash, object_uuid=str(row.object_uuid),
            field_refs=tuple(row.field_refs), state=row.state, result_ref=row.result_ref or None)

    @contextmanager
    def claim(self, *, operation_ref, actor_ref, scope_ref, request_hash=None,
              object_uuid=None, field_refs=()):
        require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
        for value in (operation_ref, actor_ref, scope_ref):
            reference(value)
        path = self.store.root / ('operation-' + content_hash(operation_ref) + '.lock')
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                    not info.st_mode & 0o077 and info.st_nlink == 1, ReasonCode.AUTHORIZATION_DENIED)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                require(False, ReasonCode.DELIVERY_UNKNOWN)
            row = PrivateFileOperation.objects.filter(operation_ref=operation_ref).first()
            if row is None:
                require(request_hash is not None, ReasonCode.DELIVERY_UNKNOWN)
                value = FileUploadOperation(schema_version=FileUploadOperation.SCHEMA,
                    operation_ref=operation_ref, actor_ref=actor_ref, scope_ref=scope_ref,
                    request_hash=request_hash, object_uuid=object_uuid, field_refs=field_refs,
                    state='preparing', result_ref=None)
                row = PrivateFileOperation.objects.create(operation_ref=value.operation_ref,
                    actor_ref=value.actor_ref, scope_ref=value.scope_ref, request_hash=value.request_hash,
                    object_uuid=value.object_uuid, field_refs=list(value.field_refs))
            require((row.actor_ref, row.scope_ref) == (actor_ref, scope_ref), ReasonCode.AUTHORIZATION_DENIED)
            if request_hash is not None:
                require(row.request_hash == request_hash and tuple(row.field_refs) == field_refs,
                        ReasonCode.IDEMPOTENCY_CONFLICT)
            yield self._snapshot(row)
        finally:
            os.close(fd)

    def retained(self, operation, context, input_hash):
        """Reconstruct an interrupted registration only from the pre-I/O intention."""
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        require(row.state in ('preparing', 'prepared'), ReasonCode.AUTHORIZATION_DENIED)
        require(context.object_uuid == operation.object_uuid and context.field_ref in operation.field_refs,
                ReasonCode.REPORT_MISMATCH)
        item = row.files.get(context.field_ref)
        if item is None:
            return None
        require(item['context'] == context.to_wire() and item['input_hash'] == input_hash,
                ReasonCode.IDEMPOTENCY_CONFLICT)
        return self.store.recover_candidate(StoredObject.from_wire(item['stored']), context)

    def stage(self, operation, envelope, context, input_hash):
        encoded = canonical_bytes(envelope)
        ciphertext_hash = hashlib.sha256(encoded).hexdigest()
        identity = content_hash(dict(project=context.project_ref, environment=context.environment,
            object_uuid=context.object_uuid, version=context.object_version, field=context.field_ref))
        stored = StoredObject(schema_version=StoredObject.SCHEMA,
            object_ref='private/' + content_hash({'context': identity, 'ciphertext': ciphertext_hash}),
            version=context.object_version, ciphertext_hash=ciphertext_hash, size_bytes=len(encoded), state='candidate')
        # The path and expected digest commit before write_candidate can open a file.
        with transaction.atomic():
            row = PrivateFileOperation.objects.select_for_update().get(operation_ref=operation.operation_ref)
            require(row.state == 'preparing' and context.field_ref not in row.files,
                    ReasonCode.DELIVERY_UNKNOWN)
            row.files = {**row.files, context.field_ref: {'context': context.to_wire(),
                'input_hash': input_hash, 'stored': stored.to_wire()}}
            row.save(update_fields=['files'])
        return stored

    def confirm(self, operation, context, stored):
        with transaction.atomic():
            row = PrivateFileOperation.objects.select_for_update().get(operation_ref=operation.operation_ref)
            require(row.state in ('preparing', 'prepared'), ReasonCode.AUTHORIZATION_DENIED)
            item = row.files[context.field_ref]
            previous = StoredObject.from_wire(item['stored'])
            require(item['context'] == context.to_wire() and stored.state == 'verified' and
                    replace(previous, state='verified') == stored, ReasonCode.REPORT_MISMATCH)
            row.files = {**row.files, context.field_ref: {**item, 'stored': stored.to_wire()}}
            row.save(update_fields=['files'])

    def prepared(self, operation, *, recover=False):
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        require(row.state in ('preparing', 'prepared'), ReasonCode.AUTHORIZATION_DENIED)
        require(set(row.files) == set(operation.field_refs), ReasonCode.DELIVERY_UNKNOWN)
        for field in operation.field_refs:
            item = row.files[field]
            stored = StoredObject.from_wire(item['stored'])
            if recover:
                context = ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])})
                require(context.object_uuid == operation.object_uuid and context.field_ref == field,
                        ReasonCode.REPORT_MISMATCH)
                stored = self.store.recover_candidate(stored, context)
                if isinstance(stored, ProtectionError):
                    return stored
                self.confirm(operation, context, stored)
            require(stored.state == 'verified', ReasonCode.DELIVERY_UNKNOWN)
        row.state = 'prepared'
        row.save(update_fields=['state'])
        return self._snapshot(row)

    def commit(self, operation, result_ref):
        require(connection.in_atomic_block, ReasonCode.AUTHORIZATION_DENIED)
        reference(result_ref)
        updated = PrivateFileOperation.objects.filter(operation_ref=operation.operation_ref,
            state='prepared', result_ref='').update(state='committed', result_ref=result_ref)
        require(updated == 1, ReasonCode.DELIVERY_UNKNOWN)

    def require_committed(self, operation_ref, result_ref):
        row = PrivateFileOperation.objects.filter(operation_ref=operation_ref).first()
        require(row is not None and row.state == 'committed' and row.result_ref == result_ref,
                ReasonCode.AUTHORIZATION_DENIED)

    def retire(self, operation):
        """Called only in the owner's transaction that revokes reads and records authorization."""
        require(connection.in_atomic_block, ReasonCode.AUTHORIZATION_DENIED)
        updated = PrivateFileOperation.objects.filter(operation_ref=operation.operation_ref,
            state='committed', result_ref=operation.result_ref).update(state='retired')
        require(updated == 1, ReasonCode.DELIVERY_UNKNOWN)
        return replace(operation, state='retired')

    def abort(self, operation):
        require(connection.in_atomic_block, ReasonCode.AUTHORIZATION_DENIED)
        updated = PrivateFileOperation.objects.filter(operation_ref=operation.operation_ref,
            state__in=('preparing', 'prepared'), result_ref='').update(state='aborted')
        require(updated == 1, ReasonCode.DELIVERY_UNKNOWN)
        return replace(operation, state='aborted')

    def clean(self, operation):
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        if row.state == 'cleaned':
            return self._snapshot(row)
        # The owner commits authorization and this tombstone before deleting any file.
        require(row.state in ('aborted', 'retired'), ReasonCode.AUTHORIZATION_DENIED)
        for field, item in row.files.items():
            context = ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])})
            require(context.object_uuid == operation.object_uuid and field == context.field_ref and
                    field in operation.field_refs, ReasonCode.REPORT_MISMATCH)
            result = self.store.retire_candidate(StoredObject.from_wire(item['stored']), context)
            if isinstance(result, ProtectionError):
                return result
        row.state = 'cleaned'
        row.save(update_fields=['state'])
        return self._snapshot(row)
