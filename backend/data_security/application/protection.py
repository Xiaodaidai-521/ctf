"""Minimal port-driven protection. Production assembly remains closed in phase 2."""
from data_security.contracts import (Algorithm, AuditPort, AuditReceipt, ContractViolation,
    Coverage, Durability, Environment, EventKind, KeyPurpose, KeyStatus, Limits, Outcome,
    PayloadKind, PolicyCatalogPort, ProtectedResult, ProtectionContext, ProtectionError,
    ReasonCode, SecretMaterial, SecurityEvent, Unit)
from data_security.contracts.schema import reference, require
from data_security.core.policy import resolve_actions, validate_snapshot
from data_security.core.redaction import apply_actions, detect


class ProtectionService:
    def __init__(self, *, policies: PolicyCatalogPort, audit: AuditPort, clock, random_bytes,
                 environment: Environment, limits: Limits, field_ref: str,
                 keys=None, key_references=(), service_identity='service/protection', truncate=None):
        require(type(environment) is Environment and environment is not Environment.PRODUCTION,
                ReasonCode.AUTHORIZATION_DENIED)
        require(type(limits) is Limits and callable(clock) and callable(random_bytes), ReasonCode.INVALID_TYPE)
        reference(field_ref)
        reference(service_identity)
        if truncate is not None:
            require(truncate.algorithm is Algorithm.TRUNCATE)
        self.policies, self.audit, self.clock, self.random_bytes = policies, audit, clock, random_bytes
        self.environment, self.limits, self.field_ref = environment, limits, field_ref
        self.keys, self.key_references, self.service_identity = keys, key_references, service_identity
        self.truncate = truncate

    def _current_actions(self, context, policy_binding, findings):
        current = self.policies.snapshot(policy_binding)
        if type(current) is ProtectionError:
            raise ContractViolation(current.code)
        return resolve_actions(current, context, findings, policy_binding,
                               at=self.clock(), field_ref=self.field_ref)

    def protect(self, payload, context, policy_binding):
        trace = context.trace_id if type(context) is ProtectionContext else 'protection/service'
        stage = ReasonCode.POLICY_NOT_APPROVED
        try:
            require(type(context) is ProtectionContext and context.environment is self.environment,
                    ReasonCode.AUTHORIZATION_DENIED)
            snapshot = self.policies.snapshot(policy_binding)
            if type(snapshot) is ProtectionError:
                return ProtectionError(schema_version=ProtectionError.SCHEMA, code=snapshot.code,
                                       retryable=snapshot.retryable, trace_id=trace)
            at = self.clock()
            validate_snapshot(snapshot, policy_binding, at=at)
            findings = detect(payload, self.limits)
            if type(findings) is ProtectionError:
                raise ContractViolation(findings.code)
            actions = resolve_actions(snapshot, context, findings, policy_binding, at=at, field_ref=self.field_ref)
            stage = ReasonCode.KEY_UNAVAILABLE
            materials = []
            for name in sorted({a.algorithm.key_ref for a in actions if a.algorithm.key_ref is not None}):
                matches = [k for k in self.key_references if k.key_ref == name]
                require(len(matches) == 1 and matches[0].status is KeyStatus.ACTIVE, ReasonCode.KEY_UNAVAILABLE)
                key = matches[0]
                require(key.purpose in (KeyPurpose.LINK, KeyPurpose.PSEUDONYM) and self.keys is not None,
                        ReasonCode.KEY_UNAVAILABLE)
                secret = self.keys.resolve(key, key.purpose, self.service_identity)
                if type(secret) is ProtectionError:
                    raise ContractViolation(secret.code)
                require(type(secret) is SecretMaterial, ReasonCode.KEY_UNAVAILABLE)
                materials.append((key, bytes(secret.borrow(key.purpose))))
            protected = apply_actions(payload, actions, self.limits, materials=tuple(materials),
                environment=context.environment, domain=context.domain, scope=self.field_ref, truncate=self.truncate)
            # Coverage counts source units, not regex hits or remaining fields.
            def units(value):
                if type(value) is dict:
                    return sum(units(v) for v in value.values())
                if type(value) is list:
                    return sum(units(v) for v in value)
                return 1
            total = 1 if payload.kind is PayloadKind.TEXT else units(payload.tree.to_value())
            excluded_paths = {f.location.json_path for i, f in enumerate(findings)
                              if f'finding/{i}' not in {a.source_operation_ref for a in actions}}
            processed_paths = {a.location.json_path for a in actions}
            excluded = len(excluded_paths - processed_paths)
            coverage = Coverage(schema_version=Coverage.SCHEMA,
                unit=Unit.TEXT if payload.kind is PayloadKind.TEXT else Unit.FIELD,
                total=total, eligible=total - excluded, processed=total - excluded, excluded=excluded,
                failed=0, unknown=0, unscanned=0, version='existing-formats-coverage.v1')
            # Re-read only this exact binding, never latest. Revocation or an
            # expired exception invalidates the already-computed output.
            stage = ReasonCode.POLICY_NOT_APPROVED
            require(self._current_actions(context, policy_binding, findings) == actions,
                    ReasonCode.AUTHORIZATION_EXPIRED)
            stage = ReasonCode.AUDIT_UNAVAILABLE
            event_bytes = self.random_bytes(16)
            require(type(event_bytes) is bytes and len(event_bytes) == 16, ReasonCode.AUDIT_UNAVAILABLE)
            event = SecurityEvent(schema_version=SecurityEvent.SCHEMA, event_id='protection/' + event_bytes.hex(),
                kind=EventKind.PROTECTION, actor_ref=context.actor_ref, object_ref=context.object_ref,
                object_version=context.object_version, outcome=Outcome.SUCCEEDED, occurred_at=at,
                counts=(('hit', len(findings)), ('processed', coverage.processed), ('excluded', coverage.excluded)),
                policy_binding=policy_binding, algorithm_versions=tuple(sorted({a.algorithm.algorithm.value + '-v1' for a in actions})),
                key_versions=tuple(k.key_ref for k, _ in materials), correlation_ref=trace, reason=None)
            receipt = self.audit.record(event, Durability.DURABLE)
            if type(receipt) is ProtectionError:
                raise ContractViolation(receipt.code)
            require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                    receipt.stored_at >= at, ReasonCode.AUDIT_UNAVAILABLE)
            stage = ReasonCode.POLICY_NOT_APPROVED
            require(self._current_actions(context, policy_binding, findings) == actions,
                    ReasonCode.AUTHORIZATION_EXPIRED)
            return ProtectedResult(schema_version=ProtectedResult.SCHEMA, payload=protected,
                policy_binding=policy_binding, coverage=coverage, protection_version='protection-existing.v1', trace_id=trace)
        except ContractViolation as exc:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=exc.code, retryable=False, trace_id=trace)
        except Exception:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=stage, retryable=False, trace_id=trace)
