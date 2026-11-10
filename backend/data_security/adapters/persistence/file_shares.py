"""Expiring file references: every reader still needs the original business ACL."""
from datetime import datetime, timedelta

from django.db import DatabaseError, connection, transaction

from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, EventKind, FrozenJSON, Outcome,
    ProtectionError, ReasonCode, SecurityEventV2, content_hash,
)
from data_security.contracts.schema import require
from data_security.adapters.persistence.models import PrivateFileShare


class DjangoPrivateFileShares:
    def __init__(self, *, owners, audit, read_event, policy_binding, clock, identity):
        self.owners, self.audit, self.read_event = owners, audit, read_event
        self.policy_binding, self.clock, self.identity = policy_binding, clock, identity

    def _current(self, user, target):
        owner = self.owners[target['domain']]
        if target['domain'] == 'resources':
            result = owner.authenticated_references(user=user, resource_id=target['object_id'])
            if isinstance(result, ProtectionError):
                require(False, result.code)
            selected = next((item for item in result if item[0] == target['field']), None)
            require(selected is not None, ReasonCode.AUTHORIZATION_DENIED)
            stored = selected[2]
        else:
            result = owner.authenticated_reference(user=user, ticket_id=target['ticket_id'],
                attachment_id=target['object_id'])
            if isinstance(result, ProtectionError):
                require(False, result.code)
            stored = result[1]
        return content_hash(stored)

    def _record(self, row, *, operation, actor_ref):
        event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
            event_id=f'private-share/{row.share_id}/{operation}', kind=EventKind.AUTHORIZATION,
            actor_ref=actor_ref, object_ref='private-share/' + str(row.share_id), object_version='1',
            outcome=Outcome.SUCCEEDED, occurred_at=self.clock(), counts=(('records', 1),),
            policy_binding=self.policy_binding, algorithm_versions=('private-share.' + operation + '.v1',),
            key_versions=(), correlation_ref=row.operation_ref, reason=None,
            evidence_hashes=(('report', content_hash(row.document)),))
        receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
        if isinstance(receipt, ProtectionError):
            require(False, receipt.code)
        require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                ReasonCode.AUDIT_UNAVAILABLE)

    def _load(self, share_id, *, terminal=False):
        row = PrivateFileShare.objects.filter(share_id=share_id).first()
        require(row is not None, ReasonCode.AUTHORIZATION_DENIED)
        document = row.document
        event_id = f'private-share/{row.share_id}/create'
        event = self.read_event(event_id)
        if isinstance(event, ProtectionError):
            require(False, event.code)
        require(type(event) is SecurityEventV2 and event.event_id == event_id and
                event.kind is EventKind.AUTHORIZATION and event.outcome is Outcome.SUCCEEDED and
                event.actor_ref == document['actor_ref'] and event.object_ref == 'private-share/' + str(row.share_id) and
                event.correlation_ref == row.operation_ref and
                event.algorithm_versions == ('private-share.create.v1',) and
                dict(event.evidence_hashes).get('report') == content_hash(document), ReasonCode.AUDIT_UNAVAILABLE)
        current = PrivateFileShare.objects.get(pk=row.pk)
        require((current.document, current.share_id, current.operation_ref) ==
                (row.document, row.share_id, row.operation_ref), ReasonCode.REPORT_MISMATCH)
        row = current
        if not terminal:
            require(row.revoked_at is None, ReasonCode.AUTHORIZATION_DENIED)
            require(self.clock() < datetime.fromisoformat(document['expires_at']), ReasonCode.AUTHORIZATION_EXPIRED)
        return row

    def create(self, *, user, operation_id, domain, object_id, ticket_id=None, field='file'):
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            target = {'domain': domain, 'object_id': str(object_id), 'ticket_id': ticket_id, 'field': field}
            source_hash = self._current(user, target)
            actor = 'user/' + str(user.pk)
            operation_ref = f'private-share/user-{user.pk}/{operation_id}'
            with transaction.atomic():
                row = PrivateFileShare.objects.select_for_update().filter(operation_ref=operation_ref).first()
                if row is None:
                    document = {'schema_version': 'ds.private-share.v1', 'actor_ref': actor,
                        'target': target, 'source_hash': source_hash,
                        'expires_at': (self.clock() + timedelta(minutes=5)).isoformat()}
                    row = PrivateFileShare.objects.create(share_id=self.identity(),
                        operation_ref=operation_ref, document=document)
                    self._record(row, operation='create', actor_ref=actor)
                else:
                    row = self._load(row.share_id)
                    require(row.document['target'] == target and row.document['source_hash'] == source_hash,
                            ReasonCode.IDEMPOTENCY_CONFLICT)
                require(self._current(user, target) == source_hash, ReasonCode.REPORT_MISMATCH)
                result = FrozenJSON({'share_id': str(row.share_id), 'expires_at': row.document['expires_at']})
            return result
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error)

    def open(self, *, user, share_id):
        try:
            row = self._load(share_id)
            target, source_hash = row.document['target'], row.document['source_hash']
            require(self._current(user, target) == source_hash, ReasonCode.REPORT_MISMATCH)
            owner = self.owners[target['domain']]
            if target['domain'] == 'resources':
                payload = owner.open_download(user=user, resource_id=target['object_id'], field=target['field'])
            else:
                payload = owner.open_download(user=user, ticket_id=target['ticket_id'], attachment_id=target['object_id'])
            if isinstance(payload, ProtectionError):
                return payload
            # Decryption/audit can wait: revocation and expiry are checked again before any byte leaves.
            current = self._load(share_id)
            require(current.document == row.document, ReasonCode.REPORT_MISMATCH)
            require(self._current(user, target) == source_hash, ReasonCode.REPORT_MISMATCH)
            return payload
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error)

    def revoke(self, *, user, share_id):
        try:
            row = self._load(share_id, terminal=True)
            require(row.document['actor_ref'] == 'user/' + str(user.pk), ReasonCode.AUTHORIZATION_DENIED)
            self._current(user, row.document['target'])
            with transaction.atomic():
                locked = PrivateFileShare.objects.select_for_update().get(pk=row.pk)
                require(locked.document == row.document, ReasonCode.REPORT_MISMATCH)
                if locked.revoked_at is None:
                    self._record(locked, operation='revoke', actor_ref=row.document['actor_ref'])
                    self._current(user, row.document['target'])
                    locked.revoked_at = self.clock()
                    locked.save(update_fields=['revoked_at'])
            return True
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error)

    @staticmethod
    def _failure(error):
        code = (error.code if isinstance(error, ContractViolation) else
                ReasonCode.DELIVERY_UNKNOWN if isinstance(error, DatabaseError) else ReasonCode.AUDIT_UNAVAILABLE)
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
            retryable=False, trace_id='private-share/operation')
