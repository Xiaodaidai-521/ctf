"""Feedback-owned private candidates and explicitly staged legacy maintenance."""
from contextlib import nullcontext
from dataclasses import replace
import hashlib
from uuid import UUID

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import DatabaseError, connection, transaction

from data_security.contracts import (
    AuditReceipt, BoundedPayload, ContractViolation, Durability, Environment, EventKind,
    MediaType, ObjectContext, Outcome, Outlet, PayloadKind, ProtectionContext, ProtectionError,
    Purpose, ReasonCode, Role, SecurityEventV2, StoredObject, content_hash,
)
from data_security.contracts.crypto import BINARY_CIPHER_FORMAT
from data_security.contracts.schema import require
from users.models import CTFUser
from . import constants
from .models import FeedbackAttachment, FeedbackTicket


class FeedbackPrivateUploads:
    def __init__(self, *, prepare, object_id, project_ref, environment, limits,
                 audit, policy_binding, clock, data_key_ref, read_event, operations=None, read_download=None,
                 maintenance=None):
        require(environment in (Environment.TEST, Environment.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
        self.prepare, self.object_id, self.project_ref = prepare, object_id, project_ref
        self.environment, self.limits = environment, limits
        self.audit, self.policy_binding, self.clock = audit, policy_binding, clock
        self.data_key_ref, self.read_event = data_key_ref, read_event
        self.operations, self.read_download = operations, read_download
        self.maintenance = maintenance

    def create(self, validated_data, *, user, ticket_id, operation_id=None):
        """Consume validated files; recheck current user and ticket ownership here."""
        trace = 'feedback-upload/create'
        try:
            require(user.is_authenticated, ReasonCode.AUTHORIZATION_DENIED)
            actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
            require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
            ticket = FeedbackTicket.objects.filter(pk=ticket_id).first()
            require(ticket is not None, ReasonCode.AUTHORIZATION_DENIED)
            teacher = actor.role in ('teacher', 'admin') or actor.is_superuser
            require(teacher or actor.pk in (ticket.student_id, ticket.submitter_id),
                    ReasonCode.AUTHORIZATION_DENIED)
            visibility = validated_data['visibility']
            require(teacher or visibility != constants.VISIBILITY_STAFF, ReasonCode.AUTHORIZATION_DENIED)
            upload = validated_data['file']
            require(isinstance(upload, InMemoryUploadedFile), ReasonCode.AUTHORIZATION_DENIED)
            upload.seek(0)
            content = upload.read(self.limits.max_bytes + 1)
            payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
                media_type=MediaType.BINARY, text=None, tree=None, binary=content, limits=self.limits)
            metadata = dict(
                original_name=(upload.name or 'attachment').rsplit('/', 1)[-1].rsplit('\\', 1)[-1],
                content_type=upload.content_type or 'application/octet-stream', size=len(content),
                sha256=hashlib.sha256(content).hexdigest(), visibility=visibility)
            identity = self.object_id()
            gate = nullcontext(None)
            if operation_id is not None:
                require(self.operations is not None, ReasonCode.SOURCE_NOT_APPROVED)
                trace = f'feedback-upload/user-{actor.pk}/{UUID(str(operation_id))}'
                gate = self.operations.claim(operation_ref=trace, actor_ref='user/' + str(actor.pk),
                    scope_ref='feedback/' + str(ticket.feedback_id), object_uuid=identity,
                    request_hash=content_hash({'metadata': metadata, 'payload': metadata['sha256']}),
                    field_refs=('feedback/attachment',))
            with gate as operation:
                if operation is not None:
                    identity = operation.object_uuid
                    if operation.state == 'committed':
                        reference = self.authenticated_reference(user=user, ticket_id=ticket_id,
                            attachment_id=operation.result_ref)
                        if isinstance(reference, ProtectionError):
                            return replace(reference, trace_id=trace)
                        return FeedbackAttachment.objects.get(attachment_id=operation.result_ref, ticket_id=ticket_id)
                    require(operation.state in ('preparing', 'prepared'), ReasonCode.AUTHORIZATION_DENIED)
                context = ObjectContext(schema_version=ObjectContext.SCHEMA, project_ref=self.project_ref,
                    environment=self.environment, object_uuid=identity, object_version='1',
                    field_ref='feedback/attachment',
                    authorization_ref=f'feedback-upload/{ticket.feedback_id}/user-{actor.pk}')
                stored = (self.prepare(payload, context, operation=operation) if operation is not None
                          else self.prepare(payload, context))
                if isinstance(stored, ProtectionError):
                    return replace(stored, trace_id=trace) if operation is not None else stored
                require(type(stored) is StoredObject and stored.state == 'verified' and
                        stored.version == context.object_version, ReasonCode.CIPHERTEXT_INVALID)
                version = 'feedback.private-upload.v2' if operation is not None else 'feedback.private-upload.v1'
                metadata['private_file'] = {'schema_version': version,
                    'context': context.to_wire(), 'stored': stored.to_wire()}
                if operation is not None:
                    operation = self.operations.prepared(operation)
                    if isinstance(operation, ProtectionError):
                        return replace(operation, trace_id=trace)
                    metadata['private_file']['operation_ref'] = operation.operation_ref
                event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                    event_id='feedback-upload/' + identity, kind=EventKind.PROTECTION,
                    actor_ref='user/' + str(actor.pk), object_ref='feedback/attachment/' + identity,
                    object_version=context.object_version, outcome=Outcome.SUCCEEDED, occurred_at=self.clock(),
                    counts=(('bytes', len(content)), ('processed', 1)), policy_binding=self.policy_binding,
                    algorithm_versions=(version, BINARY_CIPHER_FORMAT),
                    key_versions=(self.data_key_ref,), correlation_ref=context.authorization_ref, reason=None,
                    evidence_hashes=(('ciphertext', stored.ciphertext_hash), ('report', content_hash({
                        'attachment_id': identity, 'ticket_id': str(ticket.feedback_id),
                        'uploaded_by': str(actor.pk), **metadata}))))
                # Encryption and filesystem work are complete before the short DB transaction.
                with transaction.atomic():
                    attachment = FeedbackAttachment.objects.create(
                        attachment_id=identity, ticket=ticket, file='', uploaded_by=actor, **metadata)
                    receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
                    if isinstance(receipt, ProtectionError):
                        require(False, receipt.code)
                    require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                            receipt.durability is Durability.LEDGER_CONFIRMED and
                            receipt.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
                    if operation is not None:
                        current = CTFUser.objects.filter(pk=actor.pk, is_active=True).first()
                        ticket = FeedbackTicket.objects.get(pk=ticket_id)
                        require(current is not None and (current.role in ('teacher', 'admin') or current.is_superuser
                            or (current.pk in (ticket.student_id, ticket.submitter_id)
                                and visibility != constants.VISIBILITY_STAFF)), ReasonCode.AUTHORIZATION_DENIED)
                        self.operations.commit(operation, identity)
                return attachment
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError):
            code = ReasonCode.DELIVERY_UNKNOWN
        except (ValueError, TypeError, KeyError):
            code = ReasonCode.INVALID_VALUE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=trace)

    def authenticated_reference(self, *, user, ticket_id, attachment_id):
        """Return internal metadata only; current access is not permission to publish or deliver."""
        try:
            require(user.is_authenticated, ReasonCode.AUTHORIZATION_DENIED)
            actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
            require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
            attachment = FeedbackAttachment.objects.select_related('ticket').filter(
                attachment_id=attachment_id, ticket_id=ticket_id).first()
            require(attachment is not None, ReasonCode.AUTHORIZATION_DENIED)
            ticket = attachment.ticket
            teacher = actor.role in ('teacher', 'admin') or actor.is_superuser
            require(teacher or (actor.pk in (ticket.student_id, ticket.submitter_id) and
                    attachment.visibility == constants.VISIBILITY_STUDENT), ReasonCode.AUTHORIZATION_DENIED)
            inspected = self.inspect_recovery(attachment)
            if isinstance(inspected, ProtectionError):
                return inspected
            if attachment.private_file['schema_version'] == 'feedback.private-upload.v2':
                require(self.operations is not None, ReasonCode.SOURCE_NOT_APPROVED)
                self.operations.require_committed(attachment.private_file['operation_ref'], str(attachment.attachment_id))
            context, stored = inspected
            return replace(context, authorization_ref=f'feedback-read/{ticket.feedback_id}/user-{actor.pk}'), stored
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, KeyError, TypeError, ValueError):
            code = ReasonCode.AUDIT_UNAVAILABLE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='feedback-upload/reference')

    def inspect_recovery(self, attachment, *, read_event=None):
        """Authenticate stored metadata without granting a current ticket or download permission."""
        try:
            ticket = attachment.ticket
            require(not attachment.file and type(attachment.private_file) is dict, ReasonCode.AUDIT_UNAVAILABLE)
            version = attachment.private_file.get('schema_version')
            require(version in ('feedback.private-upload.v1', 'feedback.private-upload.v2') and
                    set(attachment.private_file) == ({'schema_version', 'context', 'stored', 'operation_ref'}
                    if version == 'feedback.private-upload.v2' else {'schema_version', 'context', 'stored'}),
                    ReasonCode.AUDIT_UNAVAILABLE)
            identity = str(attachment.attachment_id)
            event_id = 'feedback-upload/' + identity
            event = (read_event or self.read_event)(event_id)
            if isinstance(event, ProtectionError):
                return event
            require(type(event) is SecurityEventV2 and event.event_id == event_id and
                    event.kind is EventKind.PROTECTION and event.outcome is Outcome.SUCCEEDED,
                    ReasonCode.AUDIT_UNAVAILABLE)
            metadata_hash = content_hash({
                'attachment_id': identity, 'ticket_id': str(ticket.feedback_id),
                'uploaded_by': str(attachment.uploaded_by_id),
                **{field: getattr(attachment, field) for field in (
                    'original_name', 'content_type', 'size', 'sha256', 'visibility', 'private_file')}})
            evidence = dict(event.evidence_hashes)
            require(evidence.get('report') == metadata_hash, ReasonCode.AUDIT_UNAVAILABLE)
            original_context = ObjectContext(schema_version=ObjectContext.SCHEMA,
                project_ref=self.project_ref, environment=self.environment, object_uuid=identity,
                object_version='1', field_ref='feedback/attachment',
                authorization_ref=f'feedback-upload/{ticket.feedback_id}/user-{attachment.uploaded_by_id}')
            require(attachment.private_file['context'] == original_context.to_wire() and
                    event.actor_ref == 'user/' + str(attachment.uploaded_by_id) and
                    event.object_ref == 'feedback/attachment/' + identity and
                    event.object_version == original_context.object_version and
                    event.correlation_ref == original_context.authorization_ref and
                    event.counts == (('bytes', attachment.size), ('processed', 1)) and
                    event.algorithm_versions == (version, BINARY_CIPHER_FORMAT),
                    ReasonCode.AUDIT_UNAVAILABLE)
            stored = StoredObject.from_wire(attachment.private_file['stored'])
            require(stored.state == 'verified' and stored.version == original_context.object_version and
                    evidence.get('ciphertext') == stored.ciphertext_hash, ReasonCode.AUDIT_UNAVAILABLE)
            return original_context, stored
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, KeyError, TypeError, ValueError):
            code = ReasonCode.AUDIT_UNAVAILABLE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='feedback-upload/reference')

    def open_download(self, *, user, ticket_id, attachment_id):
        """Authenticate the complete file and current ticket access before returning bytes."""
        try:
            require(self.read_download is not None, ReasonCode.SOURCE_NOT_APPROVED)
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            reference = self.authenticated_reference(user=user, ticket_id=ticket_id, attachment_id=attachment_id)
            if isinstance(reference, ProtectionError):
                return reference
            context, stored = reference
            payload = self.read_download(stored, context)
            if isinstance(payload, ProtectionError):
                return payload
            with transaction.atomic():
                current = self.authenticated_reference(user=user, ticket_id=ticket_id, attachment_id=attachment_id)
                if isinstance(current, ProtectionError):
                    require(False, current.code)
                require(current == reference, ReasonCode.REPORT_MISMATCH)
                event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                    event_id='private-download/' + self.object_id(), kind=EventKind.AUTHORIZATION,
                    actor_ref='user/' + str(user.pk), object_ref='feedback/attachment/' + str(attachment_id),
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
                current = self.authenticated_reference(user=user, ticket_id=ticket_id, attachment_id=attachment_id)
                if isinstance(current, ProtectionError):
                    require(False, current.code)
                require(current == reference, ReasonCode.REPORT_MISMATCH)
            return payload
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='feedback-upload/download')

    def reconcile_operation(self, *, user, ticket_id, operation_id, cleanup=False):
        """Observe an owned intention or explicitly revoke and clean that exact preparation."""
        trace = 'feedback-upload/operation'
        try:
            require(self.operations is not None and user.is_authenticated, ReasonCode.AUTHORIZATION_DENIED)
            actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
            ticket = FeedbackTicket.objects.filter(pk=ticket_id).first()
            require(actor is not None and ticket is not None and (actor.role in ('teacher', 'admin')
                or actor.is_superuser or actor.pk in (ticket.student_id, ticket.submitter_id)),
                ReasonCode.AUTHORIZATION_DENIED)
            trace = f'feedback-upload/user-{actor.pk}/{UUID(str(operation_id))}'
            with self.operations.claim(operation_ref=trace, actor_ref='user/' + str(actor.pk),
                    scope_ref='feedback/' + str(ticket.feedback_id)) as operation:
                if operation.state == 'committed':
                    reference = self.authenticated_reference(user=user, ticket_id=ticket_id,
                        attachment_id=operation.result_ref)
                    if isinstance(reference, ProtectionError):
                        return replace(reference, trace_id=trace)
                if not cleanup:
                    if operation.state in ('preparing', 'prepared'):
                        result = self.operations.prepared(operation, recover=True)
                        return replace(result, trace_id=trace) if isinstance(result, ProtectionError) else result
                    return operation
                if operation.state not in ('aborted', 'retired', 'cleaned'):
                    with transaction.atomic():
                        event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                            event_id='feedback-cleanup/' + operation.object_uuid, kind=EventKind.AUTHORIZATION,
                            actor_ref=operation.actor_ref, object_ref=operation.operation_ref, object_version='1',
                            outcome=Outcome.SUCCEEDED, occurred_at=self.clock(), counts=(('records', 1),),
                            policy_binding=self.policy_binding, algorithm_versions=('private-upload.cleanup.v1',),
                            key_versions=(), correlation_ref=operation.operation_ref, reason=None,
                            evidence_hashes=(('report', operation.request_hash),))
                        receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
                        if isinstance(receipt, ProtectionError):
                            require(False, receipt.code)
                        require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                                receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                                ReasonCode.AUDIT_UNAVAILABLE)
                        if operation.state == 'committed':
                            current = self.authenticated_reference(user=user, ticket_id=ticket_id,
                                attachment_id=operation.result_ref)
                            if isinstance(current, ProtectionError):
                                require(False, current.code)
                            require(current == reference, ReasonCode.REPORT_MISMATCH)
                            operation = self.operations.retire(operation)
                        else:
                            current = CTFUser.objects.filter(pk=actor.pk, is_active=True).first()
                            ticket = FeedbackTicket.objects.filter(pk=ticket_id).first()
                            require(current is not None and ticket is not None and (current.role in ('teacher', 'admin')
                                or current.is_superuser or current.pk in (ticket.student_id, ticket.submitter_id)),
                                ReasonCode.AUTHORIZATION_DENIED)
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

    def maintain_legacy(self, *, user, ticket_id, attachment_id, operation_id, action, replaces=None):
        """Explicit old-attachment maintenance; original uploader AND current ticket ACL are required."""
        trace = 'feedback-legacy/maintenance'

        def owned(*, locked=False):
            actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
            query = FeedbackAttachment.objects.select_for_update() if locked else FeedbackAttachment.objects
            attachment = query.select_related('ticket').filter(
                attachment_id=attachment_id, ticket_id=ticket_id).first()
            require(actor is not None and attachment is not None and attachment.uploaded_by_id == actor.pk,
                    ReasonCode.AUTHORIZATION_DENIED)
            ticket = attachment.ticket
            require(actor.role in ('teacher', 'admin') or actor.is_superuser or
                    (actor.pk in (ticket.student_id, ticket.submitter_id) and
                     attachment.visibility == constants.VISIBILITY_STUDENT), ReasonCode.AUTHORIZATION_DENIED)
            return actor, attachment

        def report_hash(attachment):
            return content_hash({'attachment_id': str(attachment.attachment_id),
                'ticket_id': str(attachment.ticket.feedback_id), 'uploaded_by': str(attachment.uploaded_by_id),
                **{field: getattr(attachment, field) for field in (
                    'original_name', 'content_type', 'size', 'sha256', 'visibility', 'private_file')}})

        def old_hash(attachment):
            return content_hash({'metadata': report_hash(attachment), 'file': attachment.file.name})

        try:
            require(user.is_authenticated and self.maintenance is not None and self.operations is not None,
                    ReasonCode.AUTHORIZATION_DENIED)
            require(action in ('stage', 'rotate', 'migrate', 'quarantine', 'delete') and
                    (replaces is not None) == (action == 'rotate'), ReasonCode.INVALID_VALUE)
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            operation_id = str(UUID(str(operation_id)))
            actor, attachment = owned()
            identity = str(attachment.attachment_id)
            trace = f'feedback-legacy/{identity}/{operation_id}'
            owner_ref, scope_ref = 'feedback/attachment/' + identity, 'feedback/legacy/' + identity
            if action in ('stage', 'rotate'):
                require(attachment.file and attachment.private_file == {}, ReasonCode.SOURCE_NOT_APPROVED)
                return self.maintenance.stage(operation_ref=trace, actor_ref='user/' + str(actor.pk),
                    scope_ref=scope_ref, owner_ref=owner_ref, owner_hash=old_hash(attachment),
                    names={'feedback/attachment': attachment.file.name}, object_uuid=identity,
                    project_ref=self.project_ref,
                    authorization_ref=f'feedback-upload/{attachment.ticket.feedback_id}/user-{actor.pk}',
                    prepare=self.prepare, data_key_ref=self.data_key_ref,
                    replaces=f'feedback-legacy/{identity}/{UUID(str(replaces))}' if replaces is not None else None)
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
                require(set(row.files) == {'feedback/attachment'}, ReasonCode.DELIVERY_UNKNOWN)
                item = row.files['feedback/attachment']
                metadata = {'schema_version': 'feedback.private-upload.v2', 'context': item['context'],
                            'stored': item['stored'], 'operation_ref': trace}
                event_refs = {'feedback/attachment': ('feedback-upload/' + identity, owner_ref)}
                if action in ('migrate', 'quarantine') and source['phase'] == 'staged':
                    require(operation.state == 'prepared' and attachment.private_file == {} and
                            old_hash(attachment) == source['owner_hash'], ReasonCode.REPORT_MISMATCH)
                    require(source['data_key_ref'] == self.data_key_ref, ReasonCode.KEY_UNAVAILABLE)
                    recovery = self.maintenance.verify(operation, principal)
                    if isinstance(recovery, ProtectionError):
                        return recovery
                    with transaction.atomic():
                        _, attachment = owned(locked=True)
                        require(attachment.private_file == {} and old_hash(attachment) == source['owner_hash'],
                                ReasonCode.REPORT_MISMATCH)
                        attachment.file, attachment.private_file = '', metadata
                        attachment.size = source['sources']['feedback/attachment']['size_bytes']
                        attachment.sha256 = source['sources']['feedback/attachment']['sha256']
                        attachment.save(update_fields=['file', 'private_file', 'size', 'sha256'])
                        bound_hash = report_hash(attachment)
                        event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                            event_id='feedback-upload/' + identity, kind=EventKind.PROTECTION,
                            actor_ref=operation.actor_ref, object_ref=owner_ref, object_version='1',
                            outcome=Outcome.SUCCEEDED, occurred_at=self.clock(),
                            counts=(('bytes', attachment.size), ('processed', 1)), policy_binding=self.policy_binding,
                            algorithm_versions=('feedback.private-upload.v2', BINARY_CIPHER_FORMAT),
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
                                outcome=Outcome.SUCCEEDED, occurred_at=self.clock(), counts=(('processed', 1),),
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
                        require(not current.file and report_hash(current) == bound_hash, ReasonCode.REPORT_MISMATCH)
                        self.operations.commit(operation, identity)
                        operation = replace(operation, state='committed', result_ref=identity)
                        if action == 'quarantine':
                            operation = self.operations.retire(operation)
                        self.maintenance.bind(operation, recovery, quarantined=action == 'quarantine')
                    return operation
                require(not attachment.file and attachment.private_file == metadata and
                        operation.result_ref == identity and operation.state in ('committed', 'retired'),
                        ReasonCode.REPORT_MISMATCH)
                bound_hash = report_hash(attachment)
                verified = self.maintenance.authenticate(operation, report_hash=bound_hash, event_refs=event_refs,
                    version='feedback.private-upload.v2', read_event=self.read_event)
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
                    require(not current.file and report_hash(current) == bound_hash, ReasonCode.REPORT_MISMATCH)
                    for entry in source['sources'].values():
                        require(not FeedbackAttachment.objects.filter(file=entry['name']).exists(),
                                ReasonCode.SOURCE_NOT_APPROVED)
                    if source['phase'] not in ('delete-authorized', 'deleted'):
                        event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                            event_id='legacy-delete/' + operation_id, kind=EventKind.AUTHORIZATION,
                            actor_ref=operation.actor_ref, object_ref=trace, object_version='1',
                            outcome=Outcome.SUCCEEDED, occurred_at=self.clock(), counts=(('processed', 1),),
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
                        require(not current.file and report_hash(current) == bound_hash, ReasonCode.REPORT_MISMATCH)
                        self.maintenance.authorize_delete(operation, receipt)
                return self.maintenance.delete_sources(operation, read_event=self.read_event)
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError):
            code = ReasonCode.DELIVERY_UNKNOWN
        except (ValueError, TypeError, KeyError):
            code = ReasonCode.INVALID_VALUE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=trace)

    def reconcile(self, *, user, ticket_id, attachment_id):
        """Confirm a committed upload, not a delivery; absence never proves zero effects."""
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block,
                    ReasonCode.DELIVERY_UNKNOWN)
            with transaction.atomic():
                result = self.authenticated_reference(user=user, ticket_id=ticket_id,
                    attachment_id=attachment_id)
            return result
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='feedback-upload/reconcile')
