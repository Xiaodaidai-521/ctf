"""Explicit enrollment at the original field-write and reveal-request boundaries."""
import hashlib

from django.db import connection

from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, EventKind, Outcome, ProtectionError,
    ReasonCode, SecurityEventV2, canonical_bytes, content_hash,
)
from data_security.contracts.schema import require
from .models import RevealFieldRetention
from .reveal import FIELDS


class DjangoRevealRetention:
    def __init__(self, *, scope_ref, audit, policy_binding, clock):
        self.scope_ref, self.audit = scope_ref, audit
        self.policy_binding, self.clock = policy_binding, clock

    def _record(self, identity, *, object_ref, object_version, action, at, keys=()):
        require(connection.in_atomic_block, ReasonCode.SOURCE_NOT_APPROVED)
        digest = content_hash(identity)
        event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA, event_id=digest,
            kind=EventKind.AUTHORIZATION, actor_ref='service/security', object_ref=object_ref,
            object_version=object_version, outcome=Outcome.SUCCEEDED, occurred_at=at,
            counts=(('processed', 1),), policy_binding=self.policy_binding,
            algorithm_versions=('ds.reveal-retention.v1', action), key_versions=keys,
            correlation_ref=self.scope_ref, reason=None, evidence_hashes=(('report', digest),))
        receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
        if isinstance(receipt, ProtectionError):
            raise ContractViolation(receipt.code)
        require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                ReasonCode.AUDIT_UNAVAILABLE)
        return receipt

    def register_field(self, context, envelope):
        if context.field_ref not in FIELDS:
            return
        at = self.clock()
        digest = hashlib.sha256(canonical_bytes(envelope, include_payload=True)).hexdigest()
        identity = {'domain': 'ds.reveal-retention.v1', 'scope': self.scope_ref,
                    'context': context, 'generated_at': at, 'ciphertext_hash': digest}
        receipt = self._record(identity, object_ref=context.object_uuid, object_version=context.object_version,
            action='register-field', at=at, keys=(envelope.key.key_ref,))
        RevealFieldRetention.objects.create(scope_ref=self.scope_ref, object_ref=context.object_uuid,
            field_ref=context.field_ref, context_document=context.to_wire(), generated_at=at,
            ciphertext_hash=digest, registration=receipt.to_wire())

    def register_request(self, record):
        identity = {'domain': 'ds.reveal-retention.v1', 'scope': self.scope_ref,
                    'request': record.authorization_content()}
        return self._record(identity, object_ref=record.request_ref, object_version=record.object_version,
                            action='register-request', at=self.clock())
