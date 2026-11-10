"""Single-use reveal orchestration; owner permissions and storage stay in ports."""
from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
from typing import Callable

from data_security.contracts import (
    Approval, AuditPort, AuditReceipt, BoundedPayload, ContractViolation, CryptoPort, Durability,
    Environment, EventKind, FrozenJSON, GrantState, Limits, MediaType, Outcome, Outlet,
    PayloadKind, PolicyBinding, PolicyCatalogPort, ProtectedResult, ProtectionContext, ProtectionError,
    ProtectionPort, Purpose, ReasonCode, RevealGrant, RevealRepository, RevealRequestRecord,
    RevealRequestRepository, RevealSource, RevealSourcePort, SecurityEventV2, UnitOfWork,
    canonical_bytes, content_hash,
)
from data_security.contracts.schema import require


class RevealFlow:
    def __init__(self, *, repository: RevealRepository, sources: RevealSourcePort,
                 crypto: CryptoPort, policies: PolicyCatalogPort, policy_binding: PolicyBinding,
                 audit: AuditPort, uow_factory: Callable[[], UnitOfWork],
                 clock: Callable[[], datetime], limits: Limits,
                 requests: RevealRequestRepository | None = None,
                 protection: ProtectionPort | None = None, reason_field_ref: str = 'content/body',
                 identifier: Callable[[], str] | None = None):
        self.repository, self.sources, self.crypto = repository, sources, crypto
        self.policies, self.policy_binding, self.audit = policies, policy_binding, audit
        self.uow_factory, self.clock, self.limits = uow_factory, clock, limits
        self.requests, self.protection, self.identifier = requests, protection, identifier
        self.reason_field_ref = reason_field_ref

    def _management_policy(self, context):
        require(context.environment is Environment.EVALUATION and context.outlet is Outlet.API and
                context.domain == 'ctf' and context.purpose is Purpose.INVESTIGATION,
                ReasonCode.AUTHORIZATION_DENIED)
        selected = self.policies.snapshot(self.policy_binding)
        if isinstance(selected, ProtectionError):
            raise ContractViolation(selected.code)

    def request(self, record: RevealRequestRecord, context: ProtectionContext):
        try:
            self._management_policy(context)
            require(record.state == 'pending' and
                    (record.subject_ref, record.object_ref, record.object_version, record.purpose_ref,
                     tuple(reference for category, reference in record.fields)) ==
                    (context.actor_ref, context.object_ref, context.object_version,
                     'purpose/' + context.purpose.value, context.scope_refs), ReasonCode.AUTHORIZATION_DENIED)
            reason_context = replace(context, scope_refs=(self.reason_field_ref,))
            protected = self.protection.protect(record.reason, reason_context, self.policy_binding)
            if isinstance(protected, ProtectionError):
                raise ContractViolation(protected.code)
            require(type(protected) is ProtectedResult and protected.payload.kind is PayloadKind.TEXT and
                    protected.policy_binding == self.policy_binding and protected.trace_id == context.trace_id,
                    ReasonCode.SCOPE_INCOMPLETE)
            record = replace(record, reason=protected.payload)
            with self.uow_factory() as work:
                stored = self.requests.submit(record, context)
                if isinstance(stored, ProtectionError):
                    raise ContractViolation(stored.code)
                require(stored == record, ReasonCode.AUTHORIZATION_DENIED)
                receipt = self._record(record, context, Outcome.SUCCEEDED, None, action='request')
                if isinstance(receipt, ProtectionError):
                    raise ContractViolation(receipt.code)
                work.commit()
            return stored
        except ContractViolation as error:
            code = error.code
        except Exception:
            code = ReasonCode.AUTHORIZATION_DENIED
        return self._fail(record, context, code, action='request')

    def decide(self, request_ref: str, context: ProtectionContext, *, approved: bool):
        return self._change(request_ref, context, 'approve' if approved else 'reject')

    def revoke(self, request_ref: str, context: ProtectionContext):
        return self._change(request_ref, context, 'revoke')

    def _change(self, request_ref, context, operation):
        record = request_ref
        try:
            self._management_policy(context)
            with self.uow_factory() as work:
                record = self.requests.lock(request_ref, context, operation)
                if isinstance(record, ProtectionError):
                    raise ContractViolation(record.code)
                at = self.clock()
                if operation == 'approve':
                    require(record.state == 'pending' and context.actor_ref != record.subject_ref,
                            ReasonCode.AUTHORIZATION_DENIED)
                    reference = 'reveal/' + self.identifier()
                    values = dict(schema_version=RevealGrant.SCHEMA, grant_id=reference,
                        subject_ref=record.subject_ref, object_ref=record.object_ref,
                        object_version=record.object_version, fields=record.fields, purpose_ref=record.purpose_ref,
                        authorization_ref='authorization/' + reference, issued_at=at,
                        expires_at=at + timedelta(seconds=900))
                    approval = Approval(schema_version=Approval.SCHEMA, approval_ref='approval/' + reference,
                        requested_by=record.subject_ref, approved_by=context.actor_ref, approved_at=at,
                        content_hash=content_hash(values))
                    grant = RevealGrant(**values, approval=approval, state=GrantState.ACTIVE,
                                        consumed_at=None, revoked_at=None)
                    state = 'approved'
                elif operation == 'reject':
                    require(record.state == 'pending' and context.actor_ref != record.subject_ref,
                            ReasonCode.AUTHORIZATION_DENIED)
                    grant, state = None, 'rejected'
                else:
                    require(record.state == 'approved', ReasonCode.AUTHORIZATION_DENIED)
                    grant = replace(record.grant, state=GrantState.REVOKED, revoked_at=at)
                    state = 'revoked'
                record = replace(record, state=state, grant=grant, decided_by=context.actor_ref,
                                 decided_at=at, decision_event_ref=None)
                receipt = self._record(record, context, Outcome.SUCCEEDED, None, action=operation)
                if isinstance(receipt, ProtectionError):
                    raise ContractViolation(receipt.code)
                record = replace(record, decision_event_ref=receipt.event_id)
                stored = self.requests.put(record, context)
                if isinstance(stored, ProtectionError):
                    raise ContractViolation(stored.code)
                require(stored == record, ReasonCode.AUTHORIZATION_DENIED)
                work.commit()
            return stored
        except ContractViolation as error:
            code = error.code
        except Exception:
            code = ReasonCode.AUTHORIZATION_DENIED
        return self._fail(record if not isinstance(record, ProtectionError) else request_ref,
                          context, code, action=operation)

    def list_requests(self, context: ProtectionContext, *, offset: int, limit: int):
        try:
            self._management_policy(context)
            result = self.requests.list(context, offset=offset, limit=limit)
            if isinstance(result, ProtectionError):
                raise ContractViolation(result.code)
            return result
        except ContractViolation as error:
            code = error.code
        except Exception:
            code = ReasonCode.AUTHORIZATION_DENIED
        return self._fail('reveal-requests', context, code, action='list')

    def reveal(self, grant: RevealGrant, context: ProtectionContext) -> BoundedPayload | ProtectionError:
        return self._reveal(grant, context)

    def reveal_request(self, request_ref: str, context: ProtectionContext) -> BoundedPayload | ProtectionError:
        return self._reveal(None, context, request_ref=request_ref)

    def _reveal(self, grant, context, *, request_ref=None):
        try:
            require(context.environment in (Environment.TEST, Environment.EVALUATION) and
                    context.outlet is Outlet.API, ReasonCode.AUTHORIZATION_DENIED)
            if grant is not None:
                require((context.actor_ref, context.authorization_ref, context.object_ref,
                         context.object_version, 'purpose/' + context.purpose.value, context.scope_refs) ==
                        (grant.subject_ref, grant.authorization_ref, grant.object_ref,
                         grant.object_version, grant.purpose_ref, tuple(ref for _, ref in grant.fields)),
                        ReasonCode.AUTHORIZATION_DENIED)
            selected = self.policies.snapshot(self.policy_binding)
            if isinstance(selected, ProtectionError):
                raise ContractViolation(selected.code)
            at = self.clock()
            with self.uow_factory() as work:
                if grant is None:
                    record = self.requests.approved(request_ref, context)
                    if isinstance(record, ProtectionError):
                        raise ContractViolation(record.code)
                    require(record.grant is not None and record.purpose_ref == 'purpose/' + context.purpose.value,
                            ReasonCode.AUTHORIZATION_DENIED)
                    grant = record.grant
                    context = replace(context, authorization_ref=grant.authorization_ref,
                        object_ref=grant.object_ref, object_version=grant.object_version,
                        scope_refs=tuple(reference for category, reference in grant.fields))
                consumed = self.repository.consume(grant, context, grant.object_version, at)
                if isinstance(consumed, ProtectionError):
                    raise ContractViolation(consumed.code)
                require(consumed.consumed_at is not None and consumed.consumed_at >= at and
                        consumed == replace(grant, state=GrantState.CONSUMED, consumed_at=consumed.consumed_at),
                        ReasonCode.AUTHORIZATION_DENIED)
                source = self.sources.read(consumed, context)
                if isinstance(source, ProtectionError):
                    raise ContractViolation(source.code)
                require(type(source) is RevealSource and
                        (source.object_ref, source.object_version,
                         tuple(field.field_ref for field, envelope in source.fields)) ==
                        (grant.object_ref, grant.object_version, context.scope_refs) and
                        all(field.project_ref == context.domain and field.environment is context.environment
                            for field, envelope in source.fields), ReasonCode.AUTHORIZATION_DENIED)
                values = {}
                for field, envelope in source.fields:
                    opened = self.crypto.open(envelope, field, envelope.key)
                    if isinstance(opened, ProtectionError):
                        raise ContractViolation(opened.code)
                    require(opened.kind in (PayloadKind.TEXT, PayloadKind.JSON), ReasonCode.UNSUPPORTED_FORMAT)
                    values[field.field_ref] = opened.text if opened.kind is PayloadKind.TEXT else opened.tree.to_value()
                result = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.JSON,
                    media_type=MediaType.JSON, text=None, tree=FrozenJSON(values), binary=None, limits=self.limits)
                receipt = self._record(consumed, context, Outcome.SUCCEEDED, None,
                    evidence=(('ciphertext', hashlib.sha256(canonical_bytes(source, include_payload=True)).hexdigest()),
                              ('report', content_hash(consumed))),
                    keys=tuple(dict.fromkeys(envelope.key.key_ref for field, envelope in source.fields)))
                if isinstance(receipt, ProtectionError):
                    raise ContractViolation(receipt.code)
                work.commit()
            return result
        except ContractViolation as error:
            code = error.code
        except Exception:
            code = ReasonCode.AUTHORIZATION_DENIED
        # The consume/success event have rolled back before persisting a failure.
        return self._fail(grant if grant is not None else request_ref, context, code)

    def _fail(self, record, context, code, *, action='read'):
        outcome = Outcome.DENIED if code in (
            ReasonCode.AUTHORIZATION_DENIED, ReasonCode.AUTHORIZATION_EXPIRED,
            ReasonCode.POLICY_NOT_APPROVED, ReasonCode.SOURCE_NOT_APPROVED,
            ReasonCode.UNSUPPORTED_SCOPE,
        ) else Outcome.FAILED
        receipt = self._record(record, context, outcome, code, action=action)
        if isinstance(receipt, ProtectionError):
            return receipt
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=context.trace_id)

    def _record(self, record, context, outcome, reason, *, action='read', evidence=(), keys=()):
        try:
            at = self.clock()
            if isinstance(record, str):
                reference, object_ref, version = record, context.object_ref, context.object_version
                quantity = 0
            else:
                reference = record.grant_id if isinstance(record, RevealGrant) else record.request_ref
                object_ref, version, quantity = record.object_ref, record.object_version, len(record.fields)
            management = action != 'read'
            read_version = 'ds.reveal.v2' if outcome is Outcome.SUCCEEDED else 'ds.reveal.v1'
            if management and outcome is Outcome.SUCCEEDED:
                evidence = (('report', content_hash(record.authorization_content())),)
            event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                event_id=content_hash({'domain': 'ds.reveal-attempt.v1', 'trace': context.trace_id,
                    'grant': reference, 'at': at, 'outcome': outcome, 'reason': reason, 'action': action}),
                kind=EventKind.AUTHORIZATION if management else EventKind.REVEAL, actor_ref=context.actor_ref,
                object_ref=object_ref, object_version=version, outcome=outcome, occurred_at=at,
                counts=((('processed', 1) if management else ('records', quantity)),)
                    if outcome is Outcome.SUCCEEDED else (('failed', 1),),
                policy_binding=self.policy_binding,
                algorithm_versions=('ds.reveal-request.v1', action) if management else (read_version,),
                key_versions=keys, correlation_ref=reference, reason=reason, evidence_hashes=evidence)
            receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
            require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                    receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                    ReasonCode.AUDIT_UNAVAILABLE)
            return receipt
        except Exception:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                   retryable=False, trace_id=context.trace_id)
