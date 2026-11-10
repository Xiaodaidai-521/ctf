"""Explicit legacy-source staging, never a generic rekey or deletion authority.

Only the resource/feedback owner supplies names and current permission. Staging
keeps the old FileField and plaintext intact so the existing full DB + private
file backup can capture the source-to-candidate relation before any cutover.
"""
from contextlib import nullcontext
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from django.db import connection, transaction

from data_security.contracts import (
    AuditReceipt, BoundedPayload, ContractViolation, Durability, Environment, EventKind,
    MediaType, ObjectContext, Outcome, PayloadKind, ProtectionError, ReasonCode,
    SecurityEventV2, StoredObject, content_hash,
)
from data_security.contracts.crypto import BINARY_CIPHER_FORMAT
from data_security.contracts.schema import digest, reference, require
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject


class DjangoPrivateMaintenance:
    def __init__(self, *, operations, legacy_root, limits, verify_recovery=None):
        root = Path(legacy_root)
        require(root.is_absolute() and root == root.resolve() and
                not root.is_relative_to(operations.store.root) and
                not operations.store.root.is_relative_to(root), ReasonCode.AUTHORIZATION_DENIED)
        info = root.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and
                not info.st_mode & 0o022, ReasonCode.AUTHORIZATION_DENIED)
        require(verify_recovery is None or callable(verify_recovery), ReasonCode.INVALID_TYPE)
        self.operations, self.store, self.root = operations, operations.store, root
        self.limits, self.verify_recovery = limits, verify_recovery

    def _read_source(self, field, name):
        prefixes = {'resources/file': 'resources/', 'resources/cover_image': 'resource_covers/',
                    'feedback/attachment': 'feedback_evidence/'}
        require(field in prefixes and type(name) is str and name.startswith(prefixes[field]),
                ReasonCode.AUTHORIZATION_DENIED)
        relative = Path(name)
        require(not relative.is_absolute() and str(relative) == name and
                all(part not in ('.', '..') for part in relative.parts), ReasonCode.AUTHORIZATION_DENIED)
        path = self.root / relative
        require(path == path.resolve() and path.is_relative_to(self.root), ReasonCode.AUTHORIZATION_DENIED)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
                    ReasonCode.AUTHORIZATION_DENIED)
            require(info.st_size <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
            payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
                media_type=MediaType.BINARY, text=None, tree=None,
                binary=source.read(self.limits.max_bytes + 1), limits=self.limits)
        descriptor = {'name': name, 'sha256': hashlib.sha256(payload.binary).hexdigest(),
                      'size_bytes': len(payload.binary)}
        return path, descriptor, payload

    def load(self, operation):
        row = PrivateFileOperation.objects.get(operation_ref=operation.operation_ref)
        source = row.legacy_sources
        require(type(source) is dict and set(source) == {'schema_version', 'owner_ref', 'owner_hash',
                'root_hash', 'data_key_ref', 'replaces', 'sources', 'phase', 'recovery', 'cleanup'} and
                source['schema_version'] == 'ds.legacy-files.v1' and
                source['root_hash'] == content_hash(str(self.root)), ReasonCode.SOURCE_NOT_APPROVED)
        require(source['phase'] in ('staged', 'migrated', 'quarantined', 'delete-authorized', 'deleted') and
                type(source['sources']) is dict and set(source['sources']) == set(operation.field_refs),
                ReasonCode.REPORT_MISMATCH)
        for value in (source['owner_ref'], source['data_key_ref']):
            reference(value)
        digest(source['owner_hash'])
        for item in source['sources'].values():
            require(type(item) is dict and set(item) == {'name', 'sha256', 'size_bytes'} and
                    type(item['name']) is str and type(item['size_bytes']) is int and
                    0 <= item['size_bytes'] <= self.limits.max_bytes, ReasonCode.REPORT_MISMATCH)
            digest(item['sha256'])
        return row

    @staticmethod
    def source_hash(row):
        """Stable recovery projection; lifecycle states and later receipts are not its identity."""
        source = row.legacy_sources
        document = {name: getattr(row, name) for name in (
            'operation_ref', 'actor_ref', 'scope_ref', 'request_hash', 'field_refs', 'files')}
        document['object_uuid'] = str(row.object_uuid)
        document['legacy_sources'] = {name: source[name] for name in (
            'schema_version', 'owner_ref', 'owner_hash', 'root_hash', 'data_key_ref', 'replaces', 'sources')}
        return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':'),
            ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()

    def stage(self, *, operation_ref, actor_ref, scope_ref, owner_ref, owner_hash, names,
              object_uuid, project_ref, authorization_ref, prepare, data_key_ref, replaces=None):
        """Keep both source and old intention; replacement is restricted to unsigned B3 staging."""
        require(replaces != operation_ref, ReasonCode.IDEMPOTENCY_CONFLICT)
        previous_gate = (self.operations.claim(operation_ref=replaces, actor_ref=actor_ref, scope_ref=scope_ref)
                         if replaces is not None else nullcontext(None))
        with previous_gate as previous:
            payloads, sources, contexts = {}, {}, {}
            if previous is not None:
                old = self.load(previous)
                require(previous.state == 'prepared' and old.legacy_sources['phase'] == 'staged' and
                        old.legacy_sources['owner_ref'] == owner_ref and
                        old.legacy_sources['owner_hash'] == owner_hash and
                        {field: item['name'] for field, item in old.legacy_sources['sources'].items()} == names,
                        ReasonCode.AUTHORIZATION_DENIED)
                require(set(old.files) == set(names), ReasonCode.REPORT_MISMATCH)
                object_uuid = previous.object_uuid
                sources = old.legacy_sources['sources']
                for field, item in old.files.items():
                    context = ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])})
                    require(context.object_uuid == object_uuid and context.field_ref == field,
                            ReasonCode.REPORT_MISMATCH)
                    envelope = self.store.read_verified_ciphertext(StoredObject.from_wire(item['stored']), context)
                    if isinstance(envelope, ProtectionError):
                        return envelope
                    require(envelope.key.key_ref != data_key_ref, ReasonCode.KEY_UNAVAILABLE)
                    payload = self.store.crypto.open(envelope, context, envelope.key)
                    if isinstance(payload, ProtectionError):
                        return payload
                    require(hashlib.sha256(payload.binary).hexdigest() == sources[field]['sha256'] and
                            len(payload.binary) == sources[field]['size_bytes'], ReasonCode.HASH_MISMATCH)
                    payloads[field], contexts[field] = payload, context
            else:
                for field, name in names.items():
                    _, sources[field], payloads[field] = self._read_source(field, name)
                    contexts[field] = ObjectContext(schema_version=ObjectContext.SCHEMA,
                        project_ref=project_ref, environment=self.store.environment,
                        object_uuid=object_uuid, object_version='1', field_ref=field,
                        authorization_ref=authorization_ref)
            source = {'schema_version': 'ds.legacy-files.v1', 'owner_ref': owner_ref, 'owner_hash': owner_hash,
                'root_hash': content_hash(str(self.root)), 'data_key_ref': data_key_ref, 'replaces': replaces,
                'sources': sources, 'phase': 'staged', 'recovery': None, 'cleanup': None}
            with self.operations.claim(operation_ref=operation_ref, actor_ref=actor_ref, scope_ref=scope_ref,
                    request_hash=content_hash(source), object_uuid=object_uuid, field_refs=tuple(names)) as operation:
                require(operation.state in ('preparing', 'prepared'), ReasonCode.AUTHORIZATION_DENIED)
                with transaction.atomic():
                    row = PrivateFileOperation.objects.select_for_update().get(operation_ref=operation_ref)
                    if row.legacy_sources:
                        require(row.legacy_sources == source, ReasonCode.IDEMPOTENCY_CONFLICT)
                    else:
                        row.legacy_sources = source
                        row.save(update_fields=['legacy_sources'])
                for field, payload in payloads.items():
                    context = contexts[field]
                    # A resumed first staging uses its retained UUID, not a freshly generated one.
                    if previous is None:
                        context = replace(context, object_uuid=operation.object_uuid)
                    stored = prepare(payload, context, operation=operation)
                    if isinstance(stored, ProtectionError):
                        return stored
                    require(type(stored) is StoredObject and stored.state == 'verified',
                            ReasonCode.CIPHERTEXT_INVALID)
                return self.operations.prepared(operation)

    def verify(self, operation, principal):
        """A trusted recovered inventory must cover this exact relation and every candidate."""
        row = self.load(operation)
        require(principal.actor_ref == operation.actor_ref and principal.source_ref == operation.operation_ref and
                principal.source_version == '1' and principal.source_hash == self.source_hash(row) and
                principal.object_ref == row.legacy_sources['owner_ref'], ReasonCode.REPORT_MISMATCH)
        require(set(row.files) == set(operation.field_refs), ReasonCode.DELIVERY_UNKNOWN)
        for field, item in row.files.items():
            context = ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])})
            require(context.object_uuid == operation.object_uuid and context.field_ref == field and
                    context.environment is principal.environment and
                    context.object_version == principal.object_version, ReasonCode.REPORT_MISMATCH)
            payload = self.store.open_verified_source(StoredObject.from_wire(item['stored']), context)
            if isinstance(payload, ProtectionError):
                return payload
            source = row.legacy_sources['sources'][field]
            require(hashlib.sha256(payload.binary).hexdigest() == source['sha256'] == item['input_hash'] and
                    len(payload.binary) == source['size_bytes'], ReasonCode.HASH_MISMATCH)
        require(self.verify_recovery is not None, ReasonCode.SOURCE_NOT_APPROVED)
        receipt = self.verify_recovery(principal)
        if isinstance(receipt, ProtectionError):
            return receipt
        require(type(receipt) is AuditReceipt and receipt.durability is Durability.DURABLE and
                receipt.chain_version is None, ReasonCode.AUDIT_UNAVAILABLE)
        return receipt

    def bind(self, operation, recovery, *, quarantined):
        require(connection.in_atomic_block, ReasonCode.AUTHORIZATION_DENIED)
        row = self.load(operation)
        require(row.legacy_sources['phase'] == 'staged', ReasonCode.IDEMPOTENCY_CONFLICT)
        row.legacy_sources = {**row.legacy_sources, 'phase': 'quarantined' if quarantined else 'migrated',
                              'recovery': recovery.to_wire()}
        row.save(update_fields=['legacy_sources'])

    def authenticate(self, operation, *, report_hash, event_refs, version, read_event):
        """Reuse the upload PROTECTION chain, including its B3 source-relation digest."""
        row = self.load(operation)
        require(set(event_refs) == set(row.files) == set(operation.field_refs), ReasonCode.REPORT_MISMATCH)
        for field, (event_id, object_ref) in event_refs.items():
            event = read_event(event_id)
            if isinstance(event, ProtectionError):
                return event
            item, source = row.files[field], row.legacy_sources['sources'][field]
            require(type(event) is SecurityEventV2 and event.event_id == event_id and
                    event.kind is EventKind.PROTECTION and event.outcome is Outcome.SUCCEEDED and
                    event.actor_ref == operation.actor_ref and event.object_ref == object_ref and
                    event.object_version == item['context']['object_version'] and
                    event.correlation_ref == item['context']['authorization_ref'] and
                    event.algorithm_versions == (version, BINARY_CIPHER_FORMAT) and
                    event.key_versions == (row.legacy_sources['data_key_ref'],) and
                    event.counts == (('bytes', source['size_bytes']), ('processed', 1)) and
                    event.evidence_hashes == (('archive', self.source_hash(row)),
                        ('ciphertext', item['stored']['ciphertext_hash']), ('report', report_hash)),
                    ReasonCode.AUDIT_UNAVAILABLE)
        return None

    def authorize_delete(self, operation, receipt):
        require(connection.in_atomic_block, ReasonCode.AUTHORIZATION_DENIED)
        row = self.load(operation)
        require(row.legacy_sources['phase'] in ('migrated', 'quarantined'), ReasonCode.AUTHORIZATION_DENIED)
        row.legacy_sources = {**row.legacy_sources, 'phase': 'delete-authorized', 'cleanup': receipt.to_wire()}
        row.save(update_fields=['legacy_sources'])

    def delete_sources(self, operation, *, read_event):
        """Called under the owner's gate, after recovery, current ACL and new binding verification."""
        row = self.load(operation)
        require(row.legacy_sources['phase'] in ('delete-authorized', 'deleted'), ReasonCode.AUTHORIZATION_DENIED)
        receipt = AuditReceipt.from_wire(row.legacy_sources['cleanup'])
        event = read_event(receipt.event_id)
        if isinstance(event, ProtectionError):
            return event
        require(type(event) is SecurityEventV2 and event.event_id == receipt.event_id and
                event.kind is EventKind.AUTHORIZATION and event.outcome is Outcome.SUCCEEDED and
                event.actor_ref == operation.actor_ref and event.object_ref == operation.operation_ref and
                event.algorithm_versions == ('private-legacy.delete.v1',) and
                dict(event.evidence_hashes).get('archive') == self.source_hash(row), ReasonCode.AUDIT_UNAVAILABLE)
        if row.legacy_sources['phase'] == 'deleted':
            return operation
        for field, source in row.legacy_sources['sources'].items():
            try:
                path, current, _ = self._read_source(field, source['name'])
            except FileNotFoundError:
                # Only a previously committed exact deletion intention permits this retry.
                path = self.root / source['name']
            else:
                require(current == source, ReasonCode.HASH_MISMATCH)
                path.unlink()
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        row.legacy_sources = {**row.legacy_sources, 'phase': 'deleted'}
        row.save(update_fields=['legacy_sources'])
        return operation

    def key_inventory(self, key_ref):
        """Read-only local blockers; neither this subset nor a zero count authorizes key destruction."""
        reference(key_ref)
        found, unknown = [], []
        for row in PrivateObject.objects.order_by('object_ref').iterator():
            try:
                require(re.fullmatch(r'private/[0-9a-f]{64}', row.object_ref) is not None,
                        ReasonCode.AUTHORIZATION_DENIED)
                envelope = self.store._read_file(row.object_ref, row.size_bytes, row.ciphertext_hash)
            except (ContractViolation, OSError):
                unknown.append(row.object_ref)
                continue
            if envelope.key.key_ref == key_ref:
                found.append(row.object_ref)
        return {'key_ref': key_ref, 'references': tuple(found), 'unknown_references': tuple(unknown),
                'retirement_allowed': False,
                'uninspected': ('retained-backups', 'historical-archives', 'field-envelopes', 'unregistered-files')}
