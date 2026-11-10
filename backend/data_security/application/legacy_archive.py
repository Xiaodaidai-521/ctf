"""Approve, archive and explicitly govern v1 sources through the existing audit gateway."""
from dataclasses import replace

from data_security.contracts import (
    AuditReceipt, Durability, EventKind, Outcome, ProtectionError, Purpose,
    ReasonCode, Role, SecurityEventV2, content_hash,
)


class LegacyArchiveFlow:
    def __init__(self, *, archives, audit, read_event, recipient, policy_binding, clock, service_identity,
                 identity=None, checkpoint=None, verify_recovery=None):
        self.archives, self.audit, self.read_event = archives, audit, read_event
        self.recipient, self.policy_binding, self.clock = recipient, policy_binding, clock
        self.service_identity, self.identity = service_identity, identity
        self.checkpoint, self.verify_recovery = checkpoint, verify_recovery

    def capture(self, *, principal, expected_count, expected_tail):
        approval = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
            event_id=principal.authorization_ref, kind=EventKind.AUTHORIZATION,
            actor_ref=principal.actor_ref, object_ref='audit/legacy-v1', object_version='v1',
            outcome=Outcome.SUCCEEDED, occurred_at=self.clock(), counts=(('records', expected_count),),
            policy_binding=self.policy_binding, algorithm_versions=('legacy/v1', 'age/v1'),
            key_versions=(self.recipient.version,), correlation_ref=principal.trace_id, reason=None,
            evidence_hashes=(('report', expected_tail),))
        receipt = self.audit.record(approval, Durability.LEDGER_CONFIRMED)
        if isinstance(receipt, ProtectionError):
            return receipt
        if receipt.chain_version != 'ds.audit.v2':
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                   retryable=False, trace_id=principal.trace_id)
        context = replace(principal, actor_ref=self.service_identity, role=Role.SERVICE, purpose=Purpose.STORAGE)
        captured = self.archives.create(expected_count=expected_count, expected_tail=expected_tail,
                                        recipient=self.recipient, context=context)
        if isinstance(captured, ProtectionError):
            return captured
        stored, event = captured
        return self._bridge(stored, event, context)

    def reconcile(self, *, principal, archive_ref):
        """Only re-bridge the retained artifact; never capture again or infer zero effects."""
        context = replace(principal, actor_ref=self.service_identity, role=Role.SERVICE, purpose=Purpose.STORAGE)
        captured = self.archives.load(archive_ref, context)
        if isinstance(captured, ProtectionError):
            return captured
        stored, event, approval_ref = captured
        approval = self.read_event(approval_ref)
        if isinstance(approval, ProtectionError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=approval.code,
                                   retryable=False, trace_id=archive_ref)
        if not (type(approval) is SecurityEventV2 and approval.kind is EventKind.AUTHORIZATION
                and approval.outcome is Outcome.SUCCEEDED and approval.object_ref == 'audit/legacy-v1'
                and approval.object_version == 'v1' and approval.reason is None
                and approval.occurred_at <= event.occurred_at
                and approval.policy_binding == event.policy_binding == self.policy_binding
                and approval.counts == (('records', dict(event.counts)['records']),)
                and approval.evidence_hashes == (('report', dict(event.evidence_hashes)['report']),)
                and approval.algorithm_versions == event.algorithm_versions == ('legacy/v1', 'age/v1')
                and approval.key_versions == event.key_versions == (self.recipient.version,)):
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.REPORT_MISMATCH,
                                   retryable=False, trace_id=archive_ref)
        return self._bridge(stored, event, context)

    def verify_content(self, *, principal, archive_ref):
        """Authenticate the retained bridge before a read-only content check, without re-bridging."""
        if self.identity is None:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
                                   retryable=False, trace_id=archive_ref)
        context = replace(principal, actor_ref=self.service_identity, role=Role.SERVICE, purpose=Purpose.STORAGE)
        captured = self._authenticated_archive(archive_ref, context)
        if isinstance(captured, ProtectionError):
            return captured
        stored, event = captured
        return self.archives.verify_content(stored, event, self.identity, context)

    def govern(self, *, principal, archive_ref, operation):
        """Explicit whole-source quarantine/delete, never an automatic archive side effect."""
        if self.identity is None:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
                                   retryable=False, trace_id=archive_ref)
        if self.checkpoint is None or self.verify_recovery is None:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.SOURCE_NOT_APPROVED,
                                   retryable=False, trace_id=archive_ref)
        context = replace(principal, actor_ref=self.service_identity, role=Role.SERVICE, purpose=Purpose.STORAGE)
        captured = self._authenticated_archive(archive_ref, context)
        if isinstance(captured, ProtectionError):
            return captured
        stored, archive_event = captured
        checked = self.archives.verify_content(stored, archive_event, self.identity, context, with_source=True)
        if isinstance(checked, ProtectionError):
            return checked
        _, source = checked
        recovery = self.verify_recovery(replace(principal, source_ref='audit/legacy-v1', source_version='1',
                                                source_hash=source['content_hash']))
        if isinstance(recovery, ProtectionError):
            return recovery
        if not (type(recovery) is AuditReceipt and recovery.chain_version is None
                and recovery.durability is Durability.DURABLE):
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.SOURCE_NOT_APPROVED,
                                   retryable=False, trace_id=archive_ref)
        # The already-authenticated bridge is retrieved idempotently through the only
        # Gateway. The checkpoint callable is bound to that same sink: it checks the
        # complete chain before anchoring its tail, including any later suffix.
        bridge = self.audit.record(archive_event, Durability.LEDGER_CONFIRMED)
        if isinstance(bridge, ProtectionError):
            return bridge
        if bridge.chain_version != 'ds.audit.v2':
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                   retryable=False, trace_id=archive_ref)
        checkpoint = self.checkpoint('ds.audit.v2')
        if isinstance(checkpoint, ProtectionError):
            return checkpoint
        if not (type(checkpoint) is AuditReceipt and checkpoint.chain_version == 'ds.audit.v2'
                and checkpoint.durability is Durability.LEDGER_CONFIRMED and checkpoint.checkpoint_ref is not None
                and checkpoint.sequence >= bridge.sequence
                and (checkpoint.sequence != bridge.sequence or replace(checkpoint, checkpoint_ref=None) == bridge)):
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                   retryable=False, trace_id=archive_ref)
        retained = self.archives.read_governance(context)
        if isinstance(retained, ProtectionError):
            return retained
        previous, completed, event = None, None, None
        if retained is not None:
            previous, operations = retained
            if previous['stored'] != stored.to_wire() or previous['source'] != source:
                return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.IDEMPOTENCY_CONFLICT,
                                       retryable=False, trace_id=archive_ref)
            for recorded_event, receipt in operations.values():
                authenticated = self.read_event(recorded_event.event_id)
                if isinstance(authenticated, ProtectionError):
                    return authenticated
                if authenticated != recorded_event:
                    return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.REPORT_MISMATCH,
                                           retryable=False, trace_id=archive_ref)
                actual = self.audit.record(recorded_event, Durability.LEDGER_CONFIRMED)
                if isinstance(actual, ProtectionError):
                    return actual
                if actual != receipt:
                    return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.REPORT_MISMATCH,
                                           retryable=False, trace_id=archive_ref)
            if operation in operations:
                event, completed = operations[operation]
        if operation == 'delete' and previous is None:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.SOURCE_NOT_APPROVED,
                                   retryable=False, trace_id=archive_ref)
        if completed is None:
            proof = dict(operation=operation, source=source, bridge=bridge.to_wire(),
                         checkpoint=checkpoint.to_wire(), recovery=recovery.to_wire())
            event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                event_id=operation + '/' + archive_ref.split('/')[-1], kind=EventKind.PROTECTION,
                actor_ref=principal.actor_ref, object_ref='audit/legacy-v1',
                object_version='v1/quarantined' if operation == 'quarantine' else 'v1/deleted',
                outcome=Outcome.SUCCEEDED, occurred_at=self.clock(),
                counts=(('records', source['records']), ('processed', source['security_records'])),
                policy_binding=self.policy_binding, algorithm_versions=('legacy/v1', 'age/v1', 'legacy-source/v1'),
                key_versions=archive_event.key_versions, correlation_ref=archive_ref, reason=None,
                evidence_hashes=(('archive', stored.ciphertext_hash), ('report', content_hash(proof))))
        return self.archives.govern(stored=stored, source=source, operation=operation, event=event,
            bridge=bridge, checkpoint=checkpoint, recovery=recovery, previous=previous, completed=completed,
            record=self.audit.record, context=context)

    def _authenticated_archive(self, archive_ref, context):
        captured = self.archives.load(archive_ref, context)
        if isinstance(captured, ProtectionError):
            return captured
        stored, retained_event, _ = captured
        event = self.read_event(retained_event.event_id)
        if isinstance(event, ProtectionError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=event.code,
                                   retryable=False, trace_id=archive_ref)
        if event != retained_event:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.REPORT_MISMATCH,
                                   retryable=False, trace_id=archive_ref)
        return stored, event

    def _bridge(self, stored, event, context):
        receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
        if not (type(receipt) is AuditReceipt and receipt.chain_version == 'ds.audit.v2'):
            code = receipt.code if isinstance(receipt, ProtectionError) else ReasonCode.AUDIT_UNAVAILABLE
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                                   retryable=False, trace_id=stored.object_ref)
        confirmed = self.archives.confirm(stored, event, receipt, context)
        return confirmed if isinstance(confirmed, ProtectionError) else (stored, confirmed)
