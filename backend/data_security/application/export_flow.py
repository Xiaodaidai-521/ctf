"""Single owner of preparation, logical commit and fenced quota recovery.

Owner input loading and current authorization are explicitly injected. Production
wiring remains closed. No method acknowledges complete network delivery.
"""
import hashlib

from data_security.contracts import (
    ContractViolation, DeliveryReceipt, Durability, Environment, EventKind, MediaType, Outcome,
    Outlet, PayloadKind, ProtectionContext, ProtectionError, Purpose, QuotaReceipt, QuotaRecoveryEvent, QuotaState, ReasonCode,
    ReportRecord, SecurityEventV2, canonical_bytes, content_hash,
)
from data_security.contracts.schema import reference, require


class ExportFlow:
    def __init__(self, *, reports, authenticator, store, risk, quota, policies,
                 authorize, audit, uow_factory, clock, authorize_recovery=None,
                 request=None, object_context=None, load_input=None, executor=None,
                 crypto=None, read_event=None):
        self.reports, self.authenticator, self.store = reports, authenticator, store
        self.risk, self.quota, self.policies = risk, quota, policies
        self.authorize, self.audit = authorize, audit
        self.uow_factory, self.clock = uow_factory, clock
        self.authorize_recovery = authorize_recovery
        self.request, self.object_context = request, object_context
        self.load_input, self.executor = load_input, executor
        self.crypto, self.read_event = crypto, read_event

    def execute(self, plan, binding, context):
        """Prepare only as the persisted owner; replay never reloads raw input."""
        owned = reserved = False
        try:
            require(self.request is not None and self.object_context is not None and
                    self.load_input is not None and self.executor is not None, ReasonCode.AUTHORIZATION_DENIED)
            require(binding.environment in ('test', 'evaluation'), ReasonCode.SOURCE_NOT_APPROVED)
            require(type(context) is ProtectionContext and
                    (context.actor_ref, context.authorization_ref, context.domain, context.environment.value,
                     context.object_ref, context.object_version, context.outlet, context.purpose) ==
                    (binding.subject_ref, binding.authorization_id, binding.domain_ref, binding.environment,
                     self.object_context.object_uuid, binding.asset_version, Outlet.EXPORT, Purpose.DELIVERY) and
                    self.object_context.field_ref in context.scope_refs, ReasonCode.AUTHORIZATION_DENIED)
            record = self.reports.read(binding)
            if isinstance(record, ProtectionError):
                return record
            if record is not None:
                require(record.plan == plan and record.context == self.object_context, ReasonCode.REPORT_MISMATCH)
                previous = self.reports.delivery(binding)
                if previous is not None:
                    return previous
                # Prepared without a receipt is recovery work, not a new grant.
                raise ContractViolation(ReasonCode.DELIVERY_UNKNOWN)
            require(self.clock() < min(plan.expires_at, binding.expires_at), ReasonCode.AUTHORIZATION_EXPIRED)
            policy = self._approved_policy(plan, binding, self.object_context, expected_owner=context)
            if isinstance(policy, ProtectionError):
                return policy
            decision = self.risk.decide(self.request, binding.policy_binding)
            if isinstance(decision, ProtectionError):
                return decision
            require(decision == binding.decision_id, ReasonCode.IDEMPOTENCY_CONFLICT)
            # Admission released its risk locks. Never take a decision lock while
            # holding quota locks: begin/reserve commits before issue/claim.
            with self.uow_factory() as work:
                created = self.reports.begin(plan, binding, self.object_context)
                if isinstance(created, ProtectionError):
                    return created
                require(created is True, ReasonCode.DELIVERY_UNKNOWN)
                owned = True
                require(self.clock() < min(plan.expires_at, binding.expires_at, policy.expires_at),
                        ReasonCode.AUTHORIZATION_EXPIRED)
                hold = self.quota.reserve(binding)
                if not isinstance(hold, ProtectionError):
                    require(hold.binding == binding and hold.state is QuotaState.RESERVED,
                            ReasonCode.DELIVERY_UNKNOWN)
                    work.commit()
            if isinstance(hold, ProtectionError):
                return hold
            reserved = True
            authorization = self.risk.issue(binding)
            if isinstance(authorization, ProtectionError):
                return self._preparation_failed(binding, context, authorization)
            require(self.clock() < min(plan.expires_at, binding.expires_at), ReasonCode.AUTHORIZATION_EXPIRED)
            payload = self.load_input(plan, binding, context)
            if isinstance(payload, ProtectionError):
                return self._preparation_failed(binding, context, payload)
            candidate = self.executor.prepare(payload, plan, binding, self.object_context)
            if isinstance(candidate, ProtectionError):
                return self._preparation_failed(binding, context, candidate)
            record = ReportRecord(schema_version=ReportRecord.SCHEMA, binding=binding, plan=plan,
                context=self.object_context, stored=candidate.stored, report=candidate.report, proof=candidate.proof)
            saved = self.reports.put(record)
            if isinstance(saved, ProtectionError):
                return self._preparation_failed(binding, context, saved)
            require(saved == record, ReasonCode.REPORT_MISMATCH)
            result = self.commit(plan, binding, self.object_context)
            return self._preparation_failed(binding, context, result) if isinstance(result, ProtectionError) else result
        except ContractViolation as error:
            code = error.code
        except Exception:
            code = ReasonCode.DELIVERY_UNKNOWN
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                                  retryable=False, trace_id=binding.execution_id)
        if reserved or (owned and code is ReasonCode.DELIVERY_UNKNOWN):
            return self._preparation_failed(binding, context, failure)
        return failure

    def _preparation_failed(self, binding, context, error):
        if error.code is not ReasonCode.DELIVERY_UNKNOWN:
            if self.authorize_recovery is None:
                return error
            recovered = self.release(binding)
            return error if isinstance(recovered, QuotaReceipt) else recovered
        # Preserve all capacity on uncertainty. Only our preparation owner may
        # fence it; a competing execute never reaches this path. A committed
        # winner is left unchanged and the caller still receives UNKNOWN.
        try:
            with self.uow_factory() as work:
                previous = self.reports.abort(binding)
                if previous is not None:
                    return error
                evidence = 'flow/unknown/' + content_hash({'domain': 'ds.uncertain.v1', 'binding': binding})
                held = self.quota.reconcile(binding, None, evidence)
                if isinstance(held, ProtectionError):
                    return error
                require(held.binding == binding and held.state is QuotaState.UNKNOWN and
                        held.evidence_ref == evidence, ReasonCode.DELIVERY_UNKNOWN)
                audited = self._audit_recovery(binding, 'unknown', context, held)
                if isinstance(audited, ProtectionError):
                    return error
                work.commit()
        except Exception:
            # If the database is unavailable, even this status write is unknown.
            # Never turn that failure into zero delivery or release capacity.
            pass
        return error

    def _approved_policy(self, plan, binding, context, *, expected_owner=None):
        owner = self.authorize(plan, binding, context)
        if isinstance(owner, ProtectionError):
            return owner
        require(type(owner) is ProtectionContext, ReasonCode.AUTHORIZATION_DENIED)
        require(expected_owner is None or owner == expected_owner, ReasonCode.AUTHORIZATION_DENIED)
        require((owner.actor_ref, owner.authorization_ref, owner.domain,
                 owner.environment.value, owner.object_ref, owner.object_version) ==
                (binding.subject_ref, binding.authorization_id, binding.domain_ref,
                 binding.environment, context.object_uuid, context.object_version) and
                context.field_ref in owner.scope_refs and owner.outlet is Outlet.EXPORT and
                owner.purpose is Purpose.DELIVERY, ReasonCode.AUTHORIZATION_DENIED)
        policy = self.policies.snapshot(binding.policy_binding)
        if isinstance(policy, ProtectionError):
            return policy
        require(not policy.teaching_exceptions, ReasonCode.POLICY_NOT_APPROVED)
        rules = {(r.category, r.outlet, r.role, r.purpose): r.action for r in policy.rules}
        require(all(rules.get((a.category, owner.outlet, owner.role, owner.purpose)) == a.algorithm
                    for a in plan.actions), ReasonCode.POLICY_NOT_APPROVED)
        return policy

    def inspect_delivery(self, binding):
        """Authenticate retained output without delivery, audit writes, or quota effects."""
        try:
            require(self.crypto is not None and self.read_event is not None and
                    self.object_context is not None, ReasonCode.AUTHORIZATION_DENIED)
            require(binding.environment in ('test', 'evaluation'), ReasonCode.SOURCE_NOT_APPROVED)
            record = self.reports.read(binding)
            if isinstance(record, ProtectionError):
                return record
            require(record is not None and record.context == self.object_context, ReasonCode.REPORT_MISMATCH)
            require(self.clock() < min(record.plan.expires_at, binding.expires_at), ReasonCode.AUTHORIZATION_EXPIRED)
            policy = self._approved_policy(record.plan, binding, record.context)
            if isinstance(policy, ProtectionError):
                return policy
            authenticated = self.authenticator.verify(record.report, record.proof, binding, record.plan, record.context,
                input_hash=record.plan.input_hash, output_hash=record.report.output_hash,
                ciphertext_hash=record.stored.ciphertext_hash)
            if isinstance(authenticated, ProtectionError):
                return authenticated
            require(authenticated is True, ReasonCode.REPORT_MISMATCH)
            receipt = self.reports.delivery(binding)
            if isinstance(receipt, ProtectionError):
                return receipt
            require(receipt is not None, ReasonCode.AUTHORIZATION_DENIED)
            event = self.read_event(receipt.audit.event_id)
            if isinstance(event, ProtectionError):
                return event
            evidence = (('ciphertext', record.stored.ciphertext_hash), ('report', content_hash(record.report)))
            require(type(event) is SecurityEventV2 and
                    (event.event_id, event.kind, event.actor_ref, event.object_ref, event.object_version,
                     event.outcome, event.counts, event.policy_binding, event.algorithm_versions,
                     event.key_versions, event.correlation_ref, event.reason, event.evidence_hashes) ==
                    (content_hash({'domain': 'ds.logical-delivery.v1', 'binding': binding}), EventKind.DELIVERY,
                     binding.subject_ref, record.stored.object_ref, record.stored.version, Outcome.SUCCEEDED,
                     (('records', receipt.delivered_records),), binding.policy_binding, record.report.algorithm_versions,
                     (record.proof.key.key_ref,), binding.execution_id, None, evidence), ReasonCode.AUDIT_UNAVAILABLE)
            # Both file authentication and plaintext hashing precede the short UoW.
            envelope = self.store.read(record.stored, record.context)
            if isinstance(envelope, ProtectionError):
                return envelope
            payload = self.crypto.open(envelope, record.context, envelope.key)
            if isinstance(payload, ProtectionError):
                return payload
            require(payload.kind is PayloadKind.BINARY and payload.media_type in (MediaType.CSV, MediaType.XLSX),
                    ReasonCode.UNSUPPORTED_FORMAT)
            require(hashlib.sha256(payload.binary).hexdigest() == record.report.output_hash, ReasonCode.HASH_MISMATCH)
            return record, receipt, payload, envelope, evidence
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=binding.execution_id)

    def open_delivery(self, binding, *, attempt_ref):
        """Open an already delivered table after fresh authorization, not a network ack.

        The trusted boundary supplies the attempt reference and owner bindings.
        This never opens an upload original or repeats a logical quota operation.
        """
        try:
            reference(attempt_ref)
            inspected = self.inspect_delivery(binding)
            if isinstance(inspected, ProtectionError):
                return inspected
            record, receipt, payload, envelope, evidence = inspected
            record_hash = hashlib.sha256(canonical_bytes(record, include_payload=True)).hexdigest()
            with self.uow_factory() as work:
                previous = self.reports.lock_delivery(binding, record_hash)
                if isinstance(previous, ProtectionError):
                    return previous
                require(previous == receipt, ReasonCode.REPORT_MISMATCH)
                policy = self._approved_policy(record.plan, binding, record.context)
                if isinstance(policy, ProtectionError):
                    return policy
                permitted = self.risk.recheck_delivered(binding)
                if isinstance(permitted, ProtectionError):
                    return permitted
                require(permitted is True, ReasonCode.AUTHORIZATION_DENIED)
                settled = self.quota.read_committed(binding)
                if isinstance(settled, ProtectionError):
                    return settled
                require(settled.binding == binding and settled.state is QuotaState.COMMITTED and
                        settled.settled_amount == receipt.delivered_records and
                        settled.evidence_ref == receipt.evidence_ref, ReasonCode.REPORT_MISMATCH)
                attempt = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                    event_id=content_hash({'domain': 'ds.download-attempt.v1', 'binding': binding, 'attempt': attempt_ref}),
                    kind=EventKind.AUTHORIZATION, actor_ref=binding.subject_ref, object_ref=record.stored.object_ref,
                    object_version=record.stored.version, outcome=Outcome.SUCCEEDED, occurred_at=self.clock(),
                    counts=(('processed', 1), ('bytes', len(payload.binary))), policy_binding=binding.policy_binding,
                    algorithm_versions=record.report.algorithm_versions, key_versions=(envelope.key.key_ref,),
                    correlation_ref=attempt_ref, reason=None, evidence_hashes=evidence)
                audited = self.audit.record(attempt, Durability.LEDGER_CONFIRMED)
                if isinstance(audited, ProtectionError):
                    return audited
                require(audited.event_id == attempt.event_id and audited.stored_at >= attempt.occurred_at and
                        audited.durability is Durability.LEDGER_CONFIRMED and audited.chain_version == 'ds.audit.v2',
                        ReasonCode.AUDIT_UNAVAILABLE)
                # Recheck current source/target and policy after quota/audit
                # waiting; the earlier permission and risk locks are still held.
                policy = self._approved_policy(record.plan, binding, record.context)
                if isinstance(policy, ProtectionError):
                    return policy
                require(self.clock() < min(record.plan.expires_at, binding.expires_at, policy.expires_at),
                        ReasonCode.AUTHORIZATION_EXPIRED)
                permitted = self.risk.recheck_delivered(binding)
                if isinstance(permitted, ProtectionError):
                    return permitted
                require(permitted is True, ReasonCode.AUTHORIZATION_DENIED)
                work.commit()
            return payload
        except ContractViolation as error:
            code = error.code
        except Exception:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=binding.execution_id)

    def release(self, binding):
        """Cancel a reserved execution; the quota authority rejects unknown holds."""
        return self._finish_without_delivery(binding, 'release')

    def reconcile(self, binding):
        """Resolve to an existing delivery or atomically fence and settle at zero."""
        return self._finish_without_delivery(binding, 'reconcile')

    def _finish_without_delivery(self, binding, operation):
        try:
            require(binding.environment in ('test', 'evaluation'), ReasonCode.SOURCE_NOT_APPROVED)
            require(self.authorize_recovery is not None, ReasonCode.AUTHORIZATION_DENIED)
            with self.uow_factory() as work:
                previous = self.reports.abort(binding)
                if isinstance(previous, ProtectionError):
                    return previous
                # The injected owner checks the current recovery actor and this
                # exact binding/operation after report-lock waiting. An expired
                # export grant is neither recovery permission nor a bar to it.
                actor = self.authorize_recovery(binding, operation)
                if isinstance(actor, ProtectionError):
                    return actor
                require(type(actor) is ProtectionContext and
                        (actor.environment.value, actor.domain, actor.object_ref, actor.object_version,
                         actor.outlet, actor.purpose) ==
                        (binding.environment, binding.domain_ref, binding.execution_id, binding.asset_version,
                         Outlet.AUDIT, Purpose.SECURITY_AUDIT) and
                        binding.reservation_id in actor.scope_refs, ReasonCode.AUTHORIZATION_DENIED)
                if previous is not None:
                    return previous
                evidence = 'flow/no-delivery/' + content_hash({'domain': 'ds.abort.v1', 'binding': binding})
                if operation == 'release':
                    result = self.quota.release(binding, evidence)
                else:
                    result = self.quota.reconcile(binding, 0, evidence)
                if isinstance(result, ProtectionError):
                    return result
                expected = QuotaState.RELEASED if operation == 'release' else QuotaState.COMMITTED
                require(result.binding == binding and result.state is expected and
                        result.settled_amount == (None if operation == 'release' else 0) and
                        result.evidence_ref == evidence, ReasonCode.DELIVERY_UNKNOWN)
                audited = self._audit_recovery(binding, operation, actor, result)
                if isinstance(audited, ProtectionError):
                    return audited
                work.commit()
            return result
        except ContractViolation as error:
            code = error.code
        except Exception:
            # An uncertain UoW exit is not proof that either the fence or the
            # settlement committed. Keep state for an explicitly authorized retry.
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=binding.execution_id)

    def _audit_recovery(self, binding, operation, actor, quota):
        # Each authorized observation is audited, including status retries by a
        # different operator. The quota receipt retains its original effect time.
        at = self.clock()
        event = QuotaRecoveryEvent(schema_version=QuotaRecoveryEvent.SCHEMA,
            event_id=content_hash({'domain': 'ds.quota-recovery.v1', 'operation': operation,
                'actor': actor.actor_ref, 'authorization': actor.authorization_ref, 'quota': quota, 'at': at}),
            kind=EventKind.AUTHORIZATION, actor_ref=actor.actor_ref, authorization_ref=actor.authorization_ref,
            operation=operation, quota=quota, object_ref=binding.reservation_id, object_version=binding.asset_version,
            outcome=Outcome.UNKNOWN if operation == 'unknown' else Outcome.SUCCEEDED,
            occurred_at=at, counts=(('unknown', binding.quantity),) if operation == 'unknown' else (('records', 0),),
            policy_binding=binding.policy_binding, algorithm_versions=(), key_versions=(),
            correlation_ref=binding.execution_id, reason=None)
        audited = self.audit.record(event, Durability.LEDGER_CONFIRMED)
        if isinstance(audited, ProtectionError):
            return audited
        require(audited.event_id == event.event_id and audited.stored_at >= at and
                audited.durability is Durability.LEDGER_CONFIRMED and audited.chain_version == 'ds.audit.v2',
                ReasonCode.AUDIT_UNAVAILABLE)
        return audited

    def commit(self, plan, binding, context):
        """Finalize an owner-prepared report; callers cannot submit a success receipt."""
        try:
            require(binding.environment in ('test', 'evaluation') and
                    context.environment is not Environment.PRODUCTION, ReasonCode.SOURCE_NOT_APPROVED)
            record = self.reports.read(binding)
            if isinstance(record, ProtectionError):
                return record
            require(record is not None, ReasonCode.REPORT_MISMATCH)
            require(record.plan == plan and record.context == context, ReasonCode.REPORT_MISMATCH)
            # This is an internal status replay, not fresh permission to download.
            previous = self.reports.delivery(binding)
            if previous is not None:
                return previous
            authenticated = self.authenticator.verify(record.report, record.proof, binding, plan, context,
                input_hash=plan.input_hash, output_hash=record.report.output_hash,
                ciphertext_hash=record.stored.ciphertext_hash)
            if isinstance(authenticated, ProtectionError):
                return authenticated
            require(authenticated is True, ReasonCode.REPORT_MISMATCH)
            # Full file authentication happens before acquiring any flow locks.
            verified = self.store.verify(record.stored, context)
            if isinstance(verified, ProtectionError):
                return verified
            require(verified.object_ref == record.stored.object_ref and
                    verified.ciphertext_hash == record.stored.ciphertext_hash, ReasonCode.REPORT_MISMATCH)
            record_hash = hashlib.sha256(canonical_bytes(record, include_payload=True)).hexdigest()
            delivered = sum(sum(end - start + 1 for start, end in scope.row_ranges) - 1
                            for scope in plan.scope.sheets)
            require(all(scope.includes_header and scope.row_ranges[0][0] == 1
                        for scope in plan.scope.sheets), ReasonCode.UNSUPPORTED_SCOPE)
            require(0 <= delivered <= binding.quantity, ReasonCode.LIMIT_EXCEEDED)
            with self.uow_factory() as work:
                # One order: report -> decision -> authorization -> quota binding
                # -> quota bucket/reservation -> private object -> audit ledger.
                previous = self.reports.lock_delivery(binding, record_hash)
                if previous is not None:
                    return previous
                # Time is sampled after lock waiting; the earlier MAC does not
                # make an expired plan or authorization current again.
                require(self.clock() < min(plan.expires_at, binding.expires_at),
                        ReasonCode.AUTHORIZATION_EXPIRED)
                policy = self._approved_policy(plan, binding, context)
                if isinstance(policy, ProtectionError):
                    return policy
                consumed = self.risk.consume(binding)
                if isinstance(consumed, ProtectionError):
                    return consumed
                require(self.clock() < min(plan.expires_at, binding.expires_at, policy.expires_at),
                        ReasonCode.AUTHORIZATION_EXPIRED)
                published = self.store.publish(verified, context)
                if isinstance(published, ProtectionError):
                    return published
                require(published.state == 'published' and published.object_ref == record.stored.object_ref,
                        ReasonCode.REPORT_MISMATCH)
                settled = self.quota.commit(binding, delivered)
                if isinstance(settled, ProtectionError):
                    return settled
                require(settled.binding == binding and settled.state is QuotaState.COMMITTED and
                        settled.settled_amount == delivered, ReasonCode.DELIVERY_UNKNOWN)
                event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                    event_id=content_hash({'domain': 'ds.logical-delivery.v1', 'binding': binding}),
                    kind=EventKind.DELIVERY, actor_ref=binding.subject_ref,
                    object_ref=published.object_ref, object_version=published.version,
                    outcome=Outcome.SUCCEEDED, occurred_at=self.clock(), counts=(('records', delivered),),
                    policy_binding=binding.policy_binding, algorithm_versions=record.report.algorithm_versions,
                    key_versions=(record.proof.key.key_ref,), correlation_ref=binding.execution_id, reason=None,
                    evidence_hashes=(('ciphertext', record.stored.ciphertext_hash),
                                     ('report', content_hash(record.report))))
                audit = self.audit.record(event, Durability.LEDGER_CONFIRMED)
                if isinstance(audit, ProtectionError):
                    return audit
                require(audit.event_id == event.event_id and audit.stored_at >= event.occurred_at and
                        audit.durability is Durability.LEDGER_CONFIRMED and audit.chain_version == 'ds.audit.v2',
                        ReasonCode.AUDIT_UNAVAILABLE)
                # Publication, quota and audit can wait after consumption. Keep
                # success conditional on current authority under the retained locks.
                policy = self._approved_policy(plan, binding, context)
                if isinstance(policy, ProtectionError):
                    return policy
                require(self.clock() < min(plan.expires_at, binding.expires_at, policy.expires_at),
                        ReasonCode.AUTHORIZATION_EXPIRED)
                permitted = self.risk.recheck_delivered(binding)
                if isinstance(permitted, ProtectionError):
                    return permitted
                require(permitted is True, ReasonCode.AUTHORIZATION_DENIED)
                receipt = DeliveryReceipt(schema_version=DeliveryReceipt.SCHEMA, binding=binding,
                    outcome=Outcome.SUCCEEDED, delivered_records=delivered,
                    evidence_ref=settled.evidence_ref, audit=audit)
                saved = self.reports.record_delivery(receipt)
                if isinstance(saved, ProtectionError):
                    return saved
                require(saved == receipt, ReasonCode.DELIVERY_UNKNOWN)
                work.commit()
            return receipt
        except ContractViolation as error:
            code = error.code
        except Exception:
            # A UoW exit/connection failure is ambiguous. Never release or
            # blindly publish again; owner recovery must read authoritative state.
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=binding.execution_id)
