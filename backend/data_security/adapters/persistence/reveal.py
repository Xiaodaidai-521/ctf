"""Owner-scoped ciphertext reads in the reveal flow's same-database transaction."""
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

from django.db import DatabaseError, connection
from django.db.models import Q
from legal.models import LegalAnalysisTask, LegalReport
from legal.permissions import IsLegalReviewer
from legal.services.data_access import authorized_legal_objects
from users.models import CTFUser
from users.permissions import authorized_users

from data_security.contracts import (
    BASELINE_LIMITS, Approval, BoundedPayload, CipherEnvelope, ContractViolation, Environment, EventKind,
    FrozenJSON, GrantState, KeyPurpose, KeyStatus, MediaType, Outcome, PayloadKind, ProtectionError,
    ReasonCode, RevealField, RevealGrant, RevealRequestRecord, RevealSource, SecurityEventV2, content_hash,
)
from data_security.contracts.schema import require
from .fields import field_storage_enabled
from .models import RevealRequest


# These are disclosure fields, not detection categories or role-based approvals.
# Conversations and manual fact notes have no approved two-person read authority.
FIELDS = {
    'users.ctfuser/email': (RevealField.EMAIL, CTFUser, 'email'),
    'legal.legalanalysistask/input_text': (RevealField.EVIDENCE, LegalAnalysisTask, 'input_text'),
    'legal.legalreport/content': (RevealField.REPORT, LegalReport, 'content'),
}


class DjangoRevealRepository:
    def __init__(self, *, fields, clock, policy_binding=None, read_event=None, retention=None):
        self.fields, self.clock = fields, clock
        self.policy_binding, self.read_event, self.retention = policy_binding, read_event, retention
        self._consumed = self._context = self._source = None
        self._locked_request = self._locked_context = self._actor = None

    def _owner_query(self, fields, actors, course_id):
        require(self.fields is not None and field_storage_enabled(), ReasonCode.SOURCE_NOT_APPROVED)
        require(all(actor.is_active for actor in actors), ReasonCode.AUTHORIZATION_DENIED)
        selected = [FIELDS.get(reference) for category, reference in fields]
        require(all(item is not None and item[0] is category for item, (category, reference)
                    in zip(selected, fields)), ReasonCode.UNSUPPORTED_SCOPE)
        model = selected[0][1]
        require(all(item[1] is model for item in selected), ReasonCode.UNSUPPORTED_SCOPE)
        query = model.objects.all()
        for actor in actors:
            if model is CTFUser:
                query = query.filter(pk__in=authorized_users(actor, course_id).values('pk'))
            else:
                require(IsLegalReviewer().has_permission(SimpleNamespace(user=actor), None),
                        ReasonCode.AUTHORIZATION_DENIED)
                query = authorized_legal_objects(query, actor, course_id)
        return query, selected

    def lookup(self, context, source_id, fields, course_id):
        """Resolve a visible business row's identity, never its ciphertext or original."""
        try:
            actor = self._current_actor(context)
            query, _ = self._owner_query(fields, (actor,), course_id)
            target = query.filter(pk=source_id).values('security_uuid', 'security_revision', 'security_state').first()
            require(target is not None, ReasonCode.AUTHORIZATION_DENIED)
            require(target['security_state'] == 'sealed-v1', ReasonCode.SOURCE_NOT_APPROVED)
            return FrozenJSON({'object_ref': str(target['security_uuid']),
                'object_version': 'v' + str(target['security_revision']),
                'fields': [[category.value, reference] for category, reference in fields]})
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.AUDIT_UNAVAILABLE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=context.trace_id)

    def source(self, *, object_ref, object_version, fields, actors, course_id):
        """Lock an existing, currently authorized owner row; never read plaintext."""
        require(connection.in_atomic_block, ReasonCode.SOURCE_NOT_APPROVED)
        query, selected = self._owner_query(fields, actors, course_id)
        target = query.select_for_update().filter(security_uuid=object_ref).first()
        require(target is not None and object_version == 'v' + str(target.security_revision),
                ReasonCode.AUTHORIZATION_DENIED)
        require(target.security_state == 'sealed-v1', ReasonCode.SOURCE_NOT_APPROVED)
        entries = []
        for category, model, name in selected:
            entry = target.security_envelopes.get(name)
            require(type(entry) is dict and set(entry) == {'revision', 'envelope'} and
                    type(entry['revision']) is int and 0 < entry['revision'] <= target.security_revision,
                    ReasonCode.CIPHERTEXT_INVALID)
            envelope = CipherEnvelope.from_wire(entry['envelope'])
            key = self.fields.read_keys.get(envelope.key.key_ref)
            require(key is not None and key.purpose is KeyPurpose.DATA and
                    key.status in (KeyStatus.ACTIVE, KeyStatus.READ_ONLY) and
                    (key.key_ref, key.version, key.purpose) ==
                    (envelope.key.key_ref, envelope.key.version, envelope.key.purpose),
                    ReasonCode.KEY_UNAVAILABLE)
            entries.append((self.fields.context(target, name, entry['revision']), envelope))
        return RevealSource(schema_version=RevealSource.SCHEMA, object_ref=object_ref,
                            object_version=object_version, fields=tuple(entries))

    def consume(self, grant, context, expected_version, at):
        self._consumed = self._context = self._source = None
        try:
            require(connection.in_atomic_block and context.environment is Environment.EVALUATION,
                    ReasonCode.AUTHORIZATION_DENIED)
            row = RevealRequest.objects.select_for_update().filter(grant_id=grant.grant_id).first()
            require(row is not None and row.state == 'approved' and row.consumed_at is None and
                    row.revoked_at is None and row.grant_document == grant.to_wire(),
                    ReasonCode.AUTHORIZATION_DENIED)
            requester = CTFUser.objects.get(pk=row.requested_by_id)
            approver = CTFUser.objects.get(pk=row.approved_by_id)
            require((grant.subject_ref, grant.approval.approved_by, grant.object_ref,
                     grant.object_version, grant.purpose_ref, grant.to_wire()['fields']) ==
                    ('user/' + str(requester.pk), 'user/' + str(approver.pk), row.object_ref,
                     row.object_version, row.purpose_ref, row.fields) and
                    context.role.value == requester.role and expected_version == row.object_version,
                    ReasonCode.AUTHORIZATION_DENIED)
            source = self.source(object_ref=row.object_ref, object_version=row.object_version,
                fields=grant.fields, actors=(requester, approver), course_id=row.course_id)
            # Check expiry after both grant/owner lock waits, not at request start.
            consumed_at = self.clock()
            require(grant.issued_at <= at <= consumed_at < grant.expires_at,
                    ReasonCode.AUTHORIZATION_EXPIRED)
            consumed = replace(grant, state=GrantState.CONSUMED, consumed_at=consumed_at)
            row.state, row.consumed_at = 'consumed', consumed_at
            row.save(update_fields=['state', 'consumed_at'])
            self._consumed, self._context, self._source = consumed, context, source
            return consumed
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=context.trace_id)

    def read(self, grant, context):
        if not connection.in_atomic_block or grant != self._consumed or context != self._context:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUTHORIZATION_DENIED,
                                   retryable=False, trace_id=context.trace_id)
        return self._source

    def _current_actor(self, context):
        actor = CTFUser.objects.only('id', 'role', 'is_active', 'is_staff').get(
            pk=int(context.actor_ref.removeprefix('user/')))
        require(context.environment is Environment.EVALUATION and actor.is_active and
                context.actor_ref == 'user/' + str(actor.pk) and context.role.value == actor.role,
                ReasonCode.AUTHORIZATION_DENIED)
        return actor

    def _record_row(self, row):
        grant = None
        if row.grant_document is not None:
            # Server-owned columns only: never lift the M0 client construction ban.
            values = dict(row.grant_document)
            for name in ('issued_at', 'expires_at', 'consumed_at', 'revoked_at'):
                if values[name] is not None:
                    values[name] = datetime.fromisoformat(values[name].replace('Z', '+00:00'))
            values['fields'] = tuple((RevealField(category), reference) for category, reference in values['fields'])
            values['state'] = GrantState(values['state'])
            values['approval'] = Approval.from_wire(values['approval'])
            grant = RevealGrant(**values)
            require(grant.to_wire() == row.grant_document and grant.grant_id == row.grant_id and
                    grant.approval.approved_by == 'user/' + str(row.approved_by_id),
                    ReasonCode.AUTHORIZATION_DENIED)
            if row.state == 'consumed':
                grant = replace(grant, state=GrantState.CONSUMED, consumed_at=row.consumed_at)
        return RevealRequestRecord(schema_version=RevealRequestRecord.SCHEMA,
            request_ref=row.request_ref, subject_ref='user/' + str(row.requested_by_id), course_id=row.course_id,
            object_ref=row.object_ref, object_version=row.object_version,
            fields=tuple((RevealField(category), reference) for category, reference in row.fields),
            purpose_ref=row.purpose_ref, requested_at=row.requested_at, state=row.state, grant=grant,
            reason=BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.TEXT,
                media_type=MediaType.TEXT, text=row.reason, tree=None, binary=None, limits=BASELINE_LIMITS),
            decided_by=row.decided_by_ref, decided_at=row.decided_at, decision_event_ref=row.decision_event_ref)

    def submit(self, record, context):
        try:
            require(connection.in_atomic_block and record.state == 'pending' and
                    record.subject_ref == context.actor_ref, ReasonCode.AUTHORIZATION_DENIED)
            actor = self._current_actor(context)
            self.source(object_ref=record.object_ref, object_version=record.object_version,
                        fields=record.fields, actors=(actor,), course_id=record.course_id)
            registration = {}
            if self.retention is not None:
                receipt = self.retention.register_request(record)
                registration = {'retention_scope': self.retention.scope_ref,
                                'retention_registration': receipt.to_wire()}
            RevealRequest.objects.create(request_ref=record.request_ref, requested_by=actor,
                course_id=record.course_id, object_ref=record.object_ref, object_version=record.object_version,
                fields=[[category.value, reference] for category, reference in record.fields],
                purpose_ref=record.purpose_ref, reason=record.reason.text, requested_at=record.requested_at,
                **registration)
            return record
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=context.trace_id)

    def lock(self, request_ref, context, operation):
        self._locked_request = self._locked_context = self._actor = None
        try:
            require(connection.in_atomic_block and operation in ('approve', 'reject', 'revoke'),
                    ReasonCode.AUTHORIZATION_DENIED)
            actor = self._current_actor(context)
            row = RevealRequest.objects.select_for_update().filter(request_ref=request_ref).first()
            require(row is not None and row.state == ('approved' if operation == 'revoke' else 'pending'),
                    ReasonCode.AUTHORIZATION_DENIED)
            requester = CTFUser.objects.get(pk=row.requested_by_id)
            if operation == 'revoke':
                require(actor.pk in (row.requested_by_id, row.approved_by_id), ReasonCode.AUTHORIZATION_DENIED)
            else:
                require(actor.pk != row.requested_by_id, ReasonCode.AUTHORIZATION_DENIED)
            record = self._record_row(row)
            if operation == 'approve':
                self.source(object_ref=row.object_ref, object_version=row.object_version,
                            fields=record.fields, actors=(requester, actor), course_id=row.course_id)
            else:
                # Reject/revoke do not require a still-current ciphertext or read key.
                query, selected = self._owner_query(record.fields, (requester, actor), row.course_id)
                require(query.select_for_update().filter(security_uuid=row.object_ref).exists(),
                        ReasonCode.AUTHORIZATION_DENIED)
            self._locked_request, self._locked_context, self._actor = row, context, actor
            return record
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=context.trace_id)

    def put(self, record, context):
        try:
            row = self._locked_request
            require(connection.in_atomic_block and row is not None and context == self._locked_context and
                    record.request_ref == row.request_ref and record.decided_by == 'user/' + str(self._actor.pk) and
                    record.decision_event_ref is not None, ReasonCode.AUTHORIZATION_DENIED)
            row.state, row.decided_by_ref, row.decided_at = record.state, record.decided_by, record.decided_at
            row.decision_event_ref = record.decision_event_ref
            row.grant_id = record.grant.grant_id if record.grant is not None else None
            row.grant_document = record.grant.to_wire() if record.grant is not None else None
            if record.state == 'approved':
                row.approved_by = self._actor
            if record.state == 'revoked':
                row.revoked_at = record.grant.revoked_at
            row.save(update_fields=['state', 'decided_by_ref', 'decided_at', 'decision_event_ref',
                                    'grant_id', 'grant_document', 'approved_by', 'revoked_at'])
            return self._record_row(row)
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=context.trace_id)

    def approved(self, request_ref, context):
        try:
            require(connection.in_atomic_block and context.environment is Environment.EVALUATION,
                    ReasonCode.AUTHORIZATION_DENIED)
            row = RevealRequest.objects.select_for_update().filter(request_ref=request_ref).first()
            require(row is not None and row.state == 'approved' and row.consumed_at is None and
                    row.revoked_at is None and context.actor_ref == 'user/' + str(row.requested_by_id),
                    ReasonCode.AUTHORIZATION_DENIED)
            record = self._record_row(row)
            require(record.decision_event_ref is not None and self.read_event is not None,
                    ReasonCode.AUDIT_UNAVAILABLE)
            event = self.read_event(record.decision_event_ref)
            if isinstance(event, ProtectionError):
                require(False, event.code)
            require(type(event) is SecurityEventV2 and event.occurred_at >= record.decided_at,
                    ReasonCode.AUDIT_UNAVAILABLE)
            expected = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                event_id=record.decision_event_ref, kind=EventKind.AUTHORIZATION,
                actor_ref=record.grant.approval.approved_by, object_ref=record.object_ref,
                object_version=record.object_version, outcome=Outcome.SUCCEEDED, occurred_at=event.occurred_at,
                counts=(('processed', 1),), policy_binding=self.policy_binding,
                algorithm_versions=('ds.reveal-request.v1', 'approve'), key_versions=(),
                correlation_ref=record.request_ref, reason=None,
                evidence_hashes=(('report', content_hash(record.authorization_content())),))
            require(event == expected, ReasonCode.AUTHORIZATION_DENIED)
            return record
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=context.trace_id)

    def list(self, context, *, offset, limit):
        try:
            actor = self._current_actor(context)
            rows = RevealRequest.objects.exclude(request_ref=None).filter(
                Q(requested_by=actor) | Q(approved_by=actor) | Q(state='pending')).order_by('pk')
            result, visible = [], 0
            for row in rows.iterator(chunk_size=100):
                record = self._record_row(row)
                try:
                    query, selected = self._owner_query(record.fields, (actor,), row.course_id)
                    if not query.filter(security_uuid=row.object_ref).exists():
                        continue
                except ContractViolation as error:
                    if error.code in (ReasonCode.AUTHORIZATION_DENIED, ReasonCode.UNSUPPORTED_SCOPE):
                        continue
                    raise
                visible += 1
                if visible <= offset:
                    continue
                result.append(record)
                if len(result) == limit:
                    break
            return tuple(result)
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=context.trace_id)
