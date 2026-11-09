"""Unique policy lookup; no default policy and no second repository on failure."""
from dataclasses import replace

from data_security.contracts import (Algorithm, ContractViolation, Durability, Environment, EventKind,
    Outcome, PolicyBinding, PolicyStatus, ProtectionError, Purpose, ReasonCode, Role, SecurityEvent)
from data_security.core.policy import validate_snapshot
from data_security.contracts.schema import require


class PolicyCatalog:
    def __init__(self, *, repository, clock, management=False, audit=None):
        self.repository, self.clock = repository, clock
        self.management, self.audit = management, audit

    def snapshot(self, binding):
        try:
            result = self.repository.read(binding)
            if type(result) is ProtectionError:
                return result
            validate_snapshot(result, binding, at=self.clock())
            require(not result.teaching_exceptions, ReasonCode.POLICY_NOT_APPROVED)
            require(all(rule.action.algorithm not in (Algorithm.HMAC, Algorithm.PSEUDONYM)
                        for rule in result.rules), ReasonCode.POLICY_NOT_APPROVED)
            return result
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=error.code, retryable=False, trace_id='policy/catalog')
        except Exception:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.POLICY_NOT_APPROVED, retryable=False, trace_id='policy/catalog')

    def save_draft(self, snapshot, expected_version, context):
        return self._write(snapshot, expected_version, context, operation='draft')

    def approve(self, snapshot, approval, context):
        return self._write(snapshot, snapshot.version, context, operation='approve', approval=approval)

    def retire(self, binding, context):
        if not self.management:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUTHORIZATION_DENIED, retryable=False, trace_id=context.trace_id)
        snapshot = self.repository.read(binding)
        if type(snapshot) is ProtectionError:
            return snapshot
        return self._write(snapshot, snapshot.version, context, operation='retire')

    def _write(self, snapshot, expected_version, context, *, operation, approval=None):
        try:
            require(self.management and self.audit is not None and
                    context.environment is Environment.EVALUATION and context.role is Role.ADMIN and
                    context.purpose is Purpose.SECURITY_AUDIT and 'policy/manage' in context.scope_refs,
                    ReasonCode.AUTHORIZATION_DENIED)
            require(not snapshot.teaching_exceptions and all(rule.action.algorithm not in
                    (Algorithm.HMAC, Algorithm.PSEUDONYM) for rule in snapshot.rules),
                    ReasonCode.POLICY_NOT_APPROVED)
            if operation == 'draft':
                require(snapshot.status is PolicyStatus.DRAFT and snapshot.approval is None,
                        ReasonCode.POLICY_NOT_APPROVED)
            elif operation == 'approve':
                require(snapshot.status is PolicyStatus.DRAFT and approval.approved_by == context.actor_ref and
                        approval.approved_at <= self.clock() < snapshot.expires_at,
                        ReasonCode.AUTHORIZATION_DENIED)
                snapshot = replace(snapshot, status=PolicyStatus.APPROVED, approval=approval)
            else:
                snapshot = replace(snapshot, status=PolicyStatus.RETIRED)
            binding = PolicyBinding(schema_version=PolicyBinding.SCHEMA,
                protection_version=snapshot.version, protection_hash=snapshot.content_hash,
                risk_version='risk/disabled-phase4', risk_hash=snapshot.content_hash,
                contract_version='ds.m0.v1')
            event = SecurityEvent(schema_version=SecurityEvent.SCHEMA, event_id=context.trace_id + '/intent',
                kind=EventKind.POLICY, actor_ref=context.actor_ref, object_ref='policy/' + operation,
                object_version=snapshot.version, outcome=Outcome.UNKNOWN, occurred_at=self.clock(),
                counts=(('records', 1),), policy_binding=binding, algorithm_versions=(), key_versions=(),
                correlation_ref=context.trace_id, reason=None)
            receipt = self.audit.record(event, Durability.DURABLE)
            if type(receipt) is ProtectionError:
                return receipt
            stored = self.repository.put(snapshot, expected_version)
            if type(stored) is ProtectionError:
                return stored
            require(stored is True, ReasonCode.POLICY_NOT_APPROVED)
            receipt = self.audit.record(replace(event, event_id=context.trace_id + '/result',
                outcome=Outcome.SUCCEEDED, occurred_at=self.clock()), Durability.DURABLE)
            return receipt if type(receipt) is ProtectionError else snapshot
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=error.code, retryable=False, trace_id=context.trace_id)
