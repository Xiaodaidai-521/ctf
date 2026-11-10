"""Resource-owned private uploads and explicitly staged legacy maintenance."""
from contextlib import nullcontext
from dataclasses import replace
import hashlib
from uuid import UUID

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import DatabaseError, connection, transaction
from django.db.models import Q

from data_security.contracts import (
    AuditReceipt, BoundedPayload, ContractViolation, Durability, Environment, EventKind,
    MediaType, ObjectContext, Outcome, Outlet, PayloadKind, ProtectionContext, ProtectionError,
    Purpose, ReasonCode, Role, SecurityEventV2, StoredObject, content_hash,
)
from data_security.contracts.crypto import BINARY_CIPHER_FORMAT
from data_security.contracts.schema import require
from users.models import CTFUser

from .models import Resource


class ResourcePrivateUploads:
    def __init__(self, *, prepare, object_id, project_ref, environment, limits,
                 audit, policy_binding, clock, data_key_ref, read_event, read_source=None,
                 operations=None, read_download=None, maintenance=None):
        require(environment in (Environment.TEST, Environment.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
        self.prepare, self.object_id, self.project_ref = prepare, object_id, project_ref
        self.environment, self.limits = environment, limits
        self.audit, self.policy_binding, self.clock = audit, policy_binding, clock
        self.data_key_ref, self.read_event = data_key_ref, read_event
        self.read_source = read_source
        self.operations, self.read_download = operations, read_download
        self.maintenance = maintenance

    def create(self, validated_data, *, user, operation_id=None):
        """Validated files only. An HTTP retry names its intent, never private references."""
        trace = 'resource-upload/create'
        try:
            require(user.is_authenticated, ReasonCode.AUTHORIZATION_DENIED)
            actor = CTFUser.objects.filter(pk=user.pk, is_active=True, role__in=('teacher', 'admin')).first()
            require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
            values, payloads = dict(validated_data), {}
            for field in ('file', 'cover_image'):
                upload = values.pop(field, None)
                if upload is not None:
                    require(isinstance(upload, InMemoryUploadedFile), ReasonCode.AUTHORIZATION_DENIED)
                    upload.seek(0)
                    payloads[field] = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
                        media_type=MediaType.BINARY, text=None, tree=None,
                        binary=upload.read(self.limits.max_bytes + 1), limits=self.limits)
            require('file' in payloads, ReasonCode.MISSING_FIELD)
            identity = self.object_id()
            gate = nullcontext(None)
            if operation_id is not None:
                require(self.operations is not None, ReasonCode.SOURCE_NOT_APPROVED)
                operation_id = str(UUID(str(operation_id)))
                trace = f'resource-upload/user-{actor.pk}/{operation_id}'
                gate = self.operations.claim(operation_ref=trace, actor_ref='user/' + str(actor.pk),
                    scope_ref='resources/uploads', object_uuid=identity,
                    request_hash=content_hash({'metadata': values,
                        'files': {field: hashlib.sha256(payload.binary).hexdigest() for field, payload in payloads.items()}}),
                    field_refs=tuple('resources/' + field for field in payloads))
            with gate as operation:
                if operation is not None:
                    identity = operation.object_uuid
                    if operation.state == 'committed':
                        references = self.authenticated_references(user=user, resource_id=operation.result_ref)
                        if isinstance(references, ProtectionError):
                            return replace(references, trace_id=trace)
                        return Resource.objects.get(pk=operation.result_ref)
                    require(operation.state in ('preparing', 'prepared'), ReasonCode.AUTHORIZATION_DENIED)
                files, audit_inputs = {}, []
                for field, payload in payloads.items():
                    context = ObjectContext(schema_version=ObjectContext.SCHEMA, project_ref=self.project_ref,
                        environment=self.environment, object_uuid=identity, object_version='1',
                        field_ref='resources/' + field, authorization_ref='resource-upload/user-' + str(actor.pk))
                    stored = (self.prepare(payload, context, operation=operation) if operation is not None
                              else self.prepare(payload, context))
                    if isinstance(stored, ProtectionError):
                        return replace(stored, trace_id=trace) if operation is not None else stored
                    require(type(stored) is StoredObject and stored.state == 'verified' and
                            stored.version == context.object_version, ReasonCode.CIPHERTEXT_INVALID)
                    files[field] = {'context': context.to_wire(), 'stored': stored.to_wire()}
                    audit_inputs.append((field, context, stored, len(payload.binary)))
                version = 'resource.private-upload.v2' if operation is not None else 'resource.private-upload.v1'
                metadata = {'schema_version': version, 'files': files}
                if operation is not None:
                    operation = self.operations.prepared(operation)
                    if isinstance(operation, ProtectionError):
                        return replace(operation, trace_id=trace)
                    metadata['operation_ref'] = operation.operation_ref
                values.update(file='', cover_image=None, uploader=actor, status='pending',
                    file_size=len(payloads['file'].binary), private_files=metadata)
                # File I/O is finished. The business row, audit and result pointer commit together.
                with transaction.atomic():
                    resource = Resource.objects.create(**values)
                    metadata_hash = content_hash({
                        'resource_id': str(resource.pk), 'uploader': str(actor.pk),
                        **{field: getattr(resource, field) for field in (
                            'title', 'description', 'resource_type', 'category', 'tags',
                            'is_tutoring_reserved', 'file_size', 'private_files')},
                        **({'status': resource.status} if operation is None else {})})
                    for field, context, stored, size in audit_inputs:
                        event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                            event_id=f'resource-upload/{identity}/{field}', kind=EventKind.PROTECTION,
                            actor_ref='user/' + str(actor.pk), object_ref=f'resources/{resource.pk}/{field}',
                            object_version=context.object_version, outcome=Outcome.SUCCEEDED,
                            occurred_at=self.clock(), counts=(('bytes', size), ('processed', 1)),
                            policy_binding=self.policy_binding, algorithm_versions=(version, BINARY_CIPHER_FORMAT),
                            key_versions=(self.data_key_ref,), correlation_ref=context.authorization_ref,
                            reason=None, evidence_hashes=(('ciphertext', stored.ciphertext_hash),
                                                          ('report', metadata_hash)))
                        receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
                        if isinstance(receipt, ProtectionError):
                            require(False, receipt.code)
                        require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                                receipt.durability is Durability.LEDGER_CONFIRMED and
                                receipt.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
                    if operation is not None:
                        require(CTFUser.objects.filter(pk=actor.pk, is_active=True,
                            role__in=('teacher', 'admin')).exists(), ReasonCode.AUTHORIZATION_DENIED)
                        self.operations.commit(operation, str(resource.pk))
                return resource
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError):
            code = ReasonCode.DELIVERY_UNKNOWN
        except (ValueError, TypeError, KeyError):
            code = ReasonCode.INVALID_VALUE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=trace)

    def authenticated_references(self, *, user, resource_id):
        """Load all upload references for the current uploader or existing staff reviewer."""
        try:
            require(user.is_authenticated, ReasonCode.AUTHORIZATION_DENIED)
            actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
            require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
            resource = Resource.objects.filter(pk=resource_id).first()
            require(resource is not None and (resource.uploader_id == actor.pk or actor.is_staff),
                    ReasonCode.AUTHORIZATION_DENIED)
            references = self.inspect_recovery(resource)
            if isinstance(references, ProtectionError):
                return references
            if resource.private_files['schema_version'] == 'resource.private-upload.v2':
                require(self.operations is not None, ReasonCode.SOURCE_NOT_APPROVED)
                self.operations.require_committed(resource.private_files['operation_ref'], str(resource.pk))
            return tuple((field, replace(context,
                authorization_ref=f'resource-read/{resource.pk}/user-{actor.pk}'), stored)
                for field, context, stored in references)
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, KeyError, TypeError, ValueError):
            code = ReasonCode.AUDIT_UNAVAILABLE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='resource-upload/reference')

    def inspect_recovery(self, resource, *, read_event=None):
        """Authenticate persisted owner metadata only; not current access or publication authority."""
        try:
            require(not resource.file and not resource.cover_image and type(resource.private_files) is dict,
                    ReasonCode.AUDIT_UNAVAILABLE)
            version = resource.private_files.get('schema_version')
            require(version in ('resource.private-upload.v1', 'resource.private-upload.v2') and
                    set(resource.private_files) == ({'schema_version', 'files', 'operation_ref'}
                    if version == 'resource.private-upload.v2' else {'schema_version', 'files'}),
                    ReasonCode.AUDIT_UNAVAILABLE)
            files = resource.private_files['files']
            require(type(files) is dict and set(files) in ({'file'}, {'file', 'cover_image'}),
                    ReasonCode.AUDIT_UNAVAILABLE)
            original_context = ObjectContext(schema_version=ObjectContext.SCHEMA,
                project_ref=self.project_ref, environment=self.environment,
                object_uuid=files['file']['context']['object_uuid'], object_version='1',
                field_ref='resources/file', authorization_ref='resource-upload/user-' + str(resource.uploader_id))
            metadata_hash = content_hash({
                'resource_id': str(resource.pk), 'uploader': str(resource.uploader_id),
                **{field: getattr(resource, field) for field in (
                    'title', 'description', 'resource_type', 'category', 'tags',
                    'is_tutoring_reserved', 'file_size', 'private_files')},
                **({'status': resource.status} if version == 'resource.private-upload.v1' else {})})
            references = []
            for field in ('file', 'cover_image'):
                if field not in files:
                    continue
                item = files[field]
                expected_context = replace(original_context, field_ref='resources/' + field)
                require(type(item) is dict and set(item) == {'context', 'stored'} and
                        item['context'] == expected_context.to_wire(), ReasonCode.AUDIT_UNAVAILABLE)
                event_id = f'resource-upload/{original_context.object_uuid}/{field}'
                event = (read_event or self.read_event)(event_id)
                if isinstance(event, ProtectionError):
                    return event
                require(type(event) is SecurityEventV2 and event.event_id == event_id and
                        event.kind is EventKind.PROTECTION and event.outcome is Outcome.SUCCEEDED and
                        event.actor_ref == 'user/' + str(resource.uploader_id) and
                        event.object_ref == f'resources/{resource.pk}/{field}' and
                        event.object_version == expected_context.object_version and
                        event.correlation_ref == expected_context.authorization_ref and
                        event.algorithm_versions == (version, BINARY_CIPHER_FORMAT),
                        ReasonCode.AUDIT_UNAVAILABLE)
                evidence, counts = dict(event.evidence_hashes), dict(event.counts)
                require(evidence.get('report') == metadata_hash and set(counts) == {'bytes', 'processed'} and
                        counts['processed'] == 1 and counts['bytes'] <= self.limits.max_bytes and
                        (field != 'file' or counts['bytes'] == resource.file_size), ReasonCode.AUDIT_UNAVAILABLE)
                stored = StoredObject.from_wire(item['stored'])
                require(stored.state == 'verified' and stored.version == expected_context.object_version and
                        evidence.get('ciphertext') == stored.ciphertext_hash, ReasonCode.AUDIT_UNAVAILABLE)
                references.append((field, expected_context, stored))
            return tuple(references)
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, KeyError, TypeError, ValueError):
            code = ReasonCode.AUDIT_UNAVAILABLE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='resource-upload/reference')

    def read_original(self, *, user, resource_id):
        """Open an authenticated original for internal processing, never a download or approval."""
        try:
            require(self.read_source is not None, ReasonCode.SOURCE_NOT_APPROVED)
            require(connection.get_autocommit() and not connection.in_atomic_block,
                    ReasonCode.AUTHORIZATION_DENIED)
            references = self.authenticated_references(user=user, resource_id=resource_id)
            if isinstance(references, ProtectionError):
                return references
            _, context, stored = references[0]
            return self.read_source(stored, context)
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id='resource-upload/source')

    def open_download(self, *, user, resource_id, field='file'):
        """Owner-only originals; publication status never creates a private-file grant."""
        try:
            require(self.read_download is not None, ReasonCode.SOURCE_NOT_APPROVED)
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            references = self.authenticated_references(user=user, resource_id=resource_id)
            if isinstance(references, ProtectionError):
                return references
            selected = next((item for item in references if item[0] == field), None)
            require(selected is not None, ReasonCode.AUTHORIZATION_DENIED)
            _, context, stored = selected
            payload = self.read_download(stored, context)
            if isinstance(payload, ProtectionError):
                return payload
            with transaction.atomic():
                current = self.authenticated_references(user=user, resource_id=resource_id)
                if isinstance(current, ProtectionError):
                    require(False, current.code)
                require(current == references, ReasonCode.REPORT_MISMATCH)
                event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                    event_id='private-download/' + self.object_id(), kind=EventKind.AUTHORIZATION,
                    actor_ref='user/' + str(user.pk), object_ref=f'resources/{resource_id}/{field}',
                    object_version=context.object_version, outcome=Outcome.SUCCEEDED, occurred_at=self.clock(),
                    counts=(('bytes', len(payload.binary)),), policy_binding=self.policy_binding,
                    algorithm_versions=('private-download.authorized.v1',), key_versions=(),
                    correlation_ref=context.authorization_ref, reason=None,
                    evidence_hashes=(('ciphertext', stored.ciphertext_hash),))
                receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
                if isinstance(receipt, ProtectionError):
                    require(False, receipt.code)
                require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                        receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                        ReasonCode.AUDIT_UNAVAILABLE)
                # Audit may have waited on the chain lock; re-read the current owner before returning bytes.
                current = self.authenticated_references(user=user, resource_id=resource_id)
                if isinstance(current, ProtectionError):
                    require(False, current.code)
                require(current == references, ReasonCode.REPORT_MISMATCH)
            return payload
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='resource-upload/download')

    def reconcile_operation(self, *, user, operation_id, cleanup=False):
        """Fence the known operation, then observe or explicitly retire its own files."""
        trace = 'resource-upload/operation'
        try:
            require(self.operations is not None and user.is_authenticated, ReasonCode.AUTHORIZATION_DENIED)
            actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
            require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
            trace = f'resource-upload/user-{actor.pk}/{UUID(str(operation_id))}'
            with self.operations.claim(operation_ref=trace, actor_ref='user/' + str(actor.pk),
                    scope_ref='resources/uploads') as operation:
                if operation.state == 'committed':
                    references = self.authenticated_references(user=user, resource_id=operation.result_ref)
                    if isinstance(references, ProtectionError):
                        return replace(references, trace_id=trace)
                if not cleanup:
                    if operation.state in ('preparing', 'prepared'):
                        result = self.operations.prepared(operation, recover=True)
                        return replace(result, trace_id=trace) if isinstance(result, ProtectionError) else result
                    return operation
                if operation.state not in ('aborted', 'retired', 'cleaned'):
                    with transaction.atomic():
                        event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                            event_id='resource-cleanup/' + operation.object_uuid, kind=EventKind.AUTHORIZATION,
                            actor_ref=operation.actor_ref, object_ref=operation.operation_ref, object_version='1',
                            outcome=Outcome.SUCCEEDED, occurred_at=self.clock(), counts=(('records', len(operation.field_refs)),),
                            policy_binding=self.policy_binding, algorithm_versions=('private-upload.cleanup.v1',),
                            key_versions=(), correlation_ref=operation.operation_ref, reason=None,
                            evidence_hashes=(('report', operation.request_hash),))
                        receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
                        if isinstance(receipt, ProtectionError):
                            require(False, receipt.code)
                        require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                                receipt.durability is Durability.LEDGER_CONFIRMED and
                                receipt.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
                        require(CTFUser.objects.filter(pk=actor.pk, is_active=True).exists(),
                                ReasonCode.AUTHORIZATION_DENIED)
                        if operation.state == 'committed':
                            current = self.authenticated_references(user=user, resource_id=operation.result_ref)
                            if isinstance(current, ProtectionError):
                                require(False, current.code)
                            require(current == references, ReasonCode.REPORT_MISMATCH)
                            operation = self.operations.retire(operation)
                        else:
                            operation = self.operations.abort(operation)
                result = self.operations.clean(operation)
                return replace(result, trace_id=trace) if isinstance(result, ProtectionError) else result
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError):
            code = ReasonCode.DELIVERY_UNKNOWN
        except (ValueError, TypeError, KeyError):
            code = ReasonCode.INVALID_VALUE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=trace)

    def maintain_legacy(self, *, user, resource_id, operation_id, action, replaces=None):
        """Internal synthetic maintenance, not HTTP delivery or a staff ownership override.

        stage/rotate retain the FileFields. migrate/quarantine need a recovered
        staging relation. delete is a separate, audited removal of exact old names.
        """
        trace = 'resource-legacy/maintenance'

        def owned(*, locked=False):
            actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
            query = Resource.objects.select_for_update() if locked else Resource.objects
            resource = query.filter(pk=resource_id).first()
            require(actor is not None and resource is not None and resource.uploader_id == actor.pk,
                    ReasonCode.AUTHORIZATION_DENIED)
            return actor, resource

        def report_hash(resource):
            return content_hash({'resource_id': str(resource.pk), 'uploader': str(resource.uploader_id),
                **{field: getattr(resource, field) for field in ('title', 'description', 'resource_type',
                    'category', 'tags', 'is_tutoring_reserved', 'file_size', 'private_files')}})

        def old_hash(resource):
            return content_hash({'metadata': report_hash(resource), 'status': resource.status,
                'file': resource.file.name, 'cover_image': resource.cover_image.name or ''})

        try:
            require(user.is_authenticated and self.maintenance is not None and self.operations is not None,
                    ReasonCode.AUTHORIZATION_DENIED)
            require(action in ('stage', 'rotate', 'migrate', 'quarantine', 'delete') and
                    (replaces is not None) == (action == 'rotate'), ReasonCode.INVALID_VALUE)
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            operation_id = str(UUID(str(operation_id)))
            trace = f'resource-legacy/{resource_id}/{operation_id}'
            actor, resource = owned()
            owner_ref, scope_ref = f'resources/{resource.pk}', f'resources/legacy/{resource.pk}'
            if action in ('stage', 'rotate'):
                require(resource.file and resource.private_files == {}, ReasonCode.SOURCE_NOT_APPROVED)
                names = {'resources/file': resource.file.name}
                if resource.cover_image:
                    names['resources/cover_image'] = resource.cover_image.name
                return self.maintenance.stage(operation_ref=trace, actor_ref='user/' + str(actor.pk),
                    scope_ref=scope_ref, owner_ref=owner_ref, owner_hash=old_hash(resource), names=names,
                    object_uuid=self.object_id(), project_ref=self.project_ref,
                    authorization_ref='resource-upload/user-' + str(actor.pk), prepare=self.prepare,
                    data_key_ref=self.data_key_ref,
                    replaces=f'resource-legacy/{resource_id}/{UUID(str(replaces))}' if replaces is not None else None)
            with self.operations.claim(operation_ref=trace, actor_ref='user/' + str(actor.pk),
                    scope_ref=scope_ref) as operation:
                row = self.maintenance.load(operation)
                source = row.legacy_sources
                require(source['owner_ref'] == owner_ref, ReasonCode.REPORT_MISMATCH)
                source_hash = self.maintenance.source_hash(row)
                principal = ProtectionContext(schema_version=ProtectionContext.SCHEMA,
                    actor_ref=operation.actor_ref, authorization_ref=trace, scope_refs=operation.field_refs,
                    environment=self.environment, domain=self.project_ref, outlet=Outlet.AUDIT, purpose=Purpose.STORAGE,
                    role=Role(actor.role), object_ref=owner_ref, object_version='1', source_ref=trace,
                    source_version='1', source_hash=source_hash, trace_id=trace)
                require(set(row.files) == set(operation.field_refs), ReasonCode.DELIVERY_UNKNOWN)
                files = {field.removeprefix('resources/'): {'context': item['context'], 'stored': item['stored']}
                         for field, item in row.files.items()}
                metadata = {'schema_version': 'resource.private-upload.v2', 'files': files, 'operation_ref': trace}
                event_refs = {field: (f'resource-upload/{operation.object_uuid}/{field.removeprefix("resources/")}',
                    f'{owner_ref}/{field.removeprefix("resources/")}') for field in operation.field_refs}
                if action in ('migrate', 'quarantine') and source['phase'] == 'staged':
                    require(operation.state == 'prepared' and resource.private_files == {} and
                            old_hash(resource) == source['owner_hash'], ReasonCode.REPORT_MISMATCH)
                    require(source['data_key_ref'] == self.data_key_ref, ReasonCode.KEY_UNAVAILABLE)
                    recovery = self.maintenance.verify(operation, principal)
                    if isinstance(recovery, ProtectionError):
                        return recovery
                    with transaction.atomic():
                        actor, resource = owned(locked=True)
                        require(resource.private_files == {} and old_hash(resource) == source['owner_hash'],
                                ReasonCode.REPORT_MISMATCH)
                        resource.file, resource.cover_image, resource.private_files = '', '', metadata
                        resource.file_size = source['sources']['resources/file']['size_bytes']
                        resource.save(update_fields=['file', 'cover_image', 'private_files', 'file_size'])
                        bound_hash = report_hash(resource)
                        for field, (event_id, object_ref) in event_refs.items():
                            item = row.files[field]
                            event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA, event_id=event_id,
                                kind=EventKind.PROTECTION, actor_ref=operation.actor_ref, object_ref=object_ref,
                                object_version='1', outcome=Outcome.SUCCEEDED, occurred_at=self.clock(),
                                counts=(('bytes', source['sources'][field]['size_bytes']), ('processed', 1)),
                                policy_binding=self.policy_binding,
                                algorithm_versions=('resource.private-upload.v2', BINARY_CIPHER_FORMAT),
                                key_versions=(source['data_key_ref'],), correlation_ref=item['context']['authorization_ref'],
                                reason=None, evidence_hashes=(('archive', source_hash),
                                    ('ciphertext', item['stored']['ciphertext_hash']), ('report', bound_hash)))
                            receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
                            if isinstance(receipt, ProtectionError):
                                require(False, receipt.code)
                            require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                                    receipt.durability is Durability.LEDGER_CONFIRMED and
                                    receipt.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
                        if action == 'quarantine':
                            event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                                event_id=('legacy-quarantine/' + content_hash(trace))[:64], kind=EventKind.AUTHORIZATION,
                                actor_ref=operation.actor_ref, object_ref=trace, object_version='1',
                                outcome=Outcome.SUCCEEDED, occurred_at=self.clock(), counts=(('processed', len(files)),),
                                policy_binding=self.policy_binding, algorithm_versions=('private-legacy.quarantine.v1',),
                                key_versions=(), correlation_ref=trace, reason=None,
                                evidence_hashes=(('archive', source_hash), ('report', bound_hash)))
                            receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
                            if isinstance(receipt, ProtectionError):
                                require(False, receipt.code)
                            require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                                    receipt.durability is Durability.LEDGER_CONFIRMED and
                                    receipt.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
                        _, current = owned()
                        require(not current.file and not current.cover_image and report_hash(current) == bound_hash,
                                ReasonCode.REPORT_MISMATCH)
                        self.operations.commit(operation, str(resource.pk))
                        operation = replace(operation, state='committed', result_ref=str(resource.pk))
                        if action == 'quarantine':
                            operation = self.operations.retire(operation)
                        self.maintenance.bind(operation, recovery, quarantined=action == 'quarantine')
                    return operation
                require(not resource.file and not resource.cover_image and resource.private_files == metadata and
                        operation.result_ref == str(resource.pk) and operation.state in ('committed', 'retired'),
                        ReasonCode.REPORT_MISMATCH)
                bound_hash = report_hash(resource)
                verified = self.maintenance.authenticate(operation, report_hash=bound_hash, event_refs=event_refs,
                    version='resource.private-upload.v2', read_event=self.read_event)
                if isinstance(verified, ProtectionError):
                    return verified
                if action != 'delete':
                    require((action == 'migrate' and operation.state == 'committed') or
                            (action == 'quarantine' and operation.state == 'retired'), ReasonCode.IDEMPOTENCY_CONFLICT)
                    return operation
                recovery = self.maintenance.verify(operation, principal)
                if isinstance(recovery, ProtectionError):
                    return recovery
                with transaction.atomic():
                    _, current = owned(locked=True)
                    require(not current.file and not current.cover_image and report_hash(current) == bound_hash,
                            ReasonCode.REPORT_MISMATCH)
                    for item in source['sources'].values():
                        require(not Resource.objects.filter(Q(file=item['name']) | Q(cover_image=item['name'])).exists(),
                                ReasonCode.SOURCE_NOT_APPROVED)
                    if source['phase'] not in ('delete-authorized', 'deleted'):
                        event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                            event_id=('legacy-delete/' + content_hash(trace))[:64], kind=EventKind.AUTHORIZATION,
                            actor_ref=operation.actor_ref, object_ref=trace, object_version='1',
                            outcome=Outcome.SUCCEEDED, occurred_at=self.clock(), counts=(('processed', len(files)),),
                            policy_binding=self.policy_binding, algorithm_versions=('private-legacy.delete.v1',),
                            key_versions=(), correlation_ref=trace, reason=None,
                            evidence_hashes=(('archive', source_hash), ('report', bound_hash)))
                        receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
                        if isinstance(receipt, ProtectionError):
                            require(False, receipt.code)
                        require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                                receipt.durability is Durability.LEDGER_CONFIRMED and
                                receipt.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
                        _, current = owned()
                        require(not current.file and not current.cover_image and report_hash(current) == bound_hash,
                                ReasonCode.REPORT_MISMATCH)
                        self.maintenance.authorize_delete(operation, receipt)
                return self.maintenance.delete_sources(operation, read_event=self.read_event)
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError):
            code = ReasonCode.DELIVERY_UNKNOWN
        except (ValueError, TypeError, KeyError):
            code = ReasonCode.INVALID_VALUE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=trace)

    def reconcile(self, *, user, resource_id):
        """Confirm a committed upload, not a delivery; absence never proves zero effects."""
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block,
                    ReasonCode.DELIVERY_UNKNOWN)
            with transaction.atomic():
                result = self.authenticated_references(user=user, resource_id=resource_id)
            return result
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='resource-upload/reconcile')
