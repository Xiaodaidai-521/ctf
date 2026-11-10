"""Bind M0 executions to the original quota authority; persist effect receipts only."""
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from data_security.contracts import (
    ContractViolation, ProtectionError, QuotaReceipt, QuotaState, ReasonCode, content_hash,
)
from data_security.contracts.schema import count, reference, require
from data_security.adapters.persistence.models import QuotaExecution
from export_quota.services import QuotaConflict, QuotaError, QuotaExceeded, QuotaService


class DjangoQuotaPort:
    def __init__(self, *, environment, window_key, limit, ttl_seconds=300):
        require(environment in ('test', 'evaluation'), ReasonCode.SOURCE_NOT_APPROVED)
        reference(window_key, maximum=80)
        count(limit, 2**53 - 1)
        count(ttl_seconds, 86400)
        require(ttl_seconds > 0)
        self.environment = environment
        self.window_key = window_key
        self.limit = limit
        self.ttl_seconds = ttl_seconds

    def reserve(self, binding):
        return self._run('reserve', binding)

    def require_active(self, binding):
        return self._run('require_active', binding)

    def read_committed(self, binding):
        """Observe historical settlement only; the caller checks current download eligibility."""
        try:
            require(binding.environment == self.environment, ReasonCode.SOURCE_NOT_APPROVED)
            reference(binding.domain_ref, maximum=120)
            bound = content_hash({'binding': binding, 'window': self.window_key,
                                  'limit': self.limit, 'ttl_seconds': self.ttl_seconds})
            record = QuotaExecution.objects.filter(idempotency_key=binding.idempotency_key).first()
            require(record is not None, ReasonCode.AUTHORIZATION_DENIED)
            require((record.binding_hash, record.reservation_id) == (bound, binding.reservation_id),
                    ReasonCode.IDEMPOTENCY_CONFLICT)
            state = QuotaService.observe(reservation_id=binding.reservation_id)
            require((state.reservation_id, state.subject_id, state.data_domain, state.window_key,
                     state.request_fingerprint, state.amount) ==
                    (binding.reservation_id, binding.subject_ref, binding.domain_ref, self.window_key,
                     binding.request_fingerprint, binding.quantity), ReasonCode.IDEMPOTENCY_CONFLICT)
            require(state.state == 'committed', ReasonCode.AUTHORIZATION_DENIED)
            require(record.terminal_receipt is not None
                    and record.terminal_operation in ('commit', 'reconcile'), ReasonCode.IDEMPOTENCY_CONFLICT)
            receipt = QuotaReceipt.from_wire(record.terminal_receipt)
            require(receipt.binding == binding and receipt.state is QuotaState.COMMITTED
                    and receipt.settled_amount == state.settled_amount, ReasonCode.IDEMPOTENCY_CONFLICT)
            if record.terminal_operation == 'commit':
                evidence = 'quota/' + content_hash({'binding': bound, 'operation': 'commit',
                                                   'delivered': state.settled_amount})
                require(receipt.evidence_ref == evidence, ReasonCode.IDEMPOTENCY_CONFLICT)
            # Reconciliation evidence remains the original persisted reference.
            return receipt
        except ContractViolation as error:
            code = error.code
        except QuotaError:
            code = ReasonCode.AUTHORIZATION_DENIED
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=binding.execution_id)

    def active_until(self, binding):
        """M6 risk callback deadline, checked under the same full-binding locks.

        The risk service's outer transaction retains these locks. This is not a
        second reservation or a deadline inferred from the execution binding.
        """
        return self._run('active_until', binding)

    def commit(self, binding, delivered):
        return self._run('commit', binding, delivered=delivered)

    def release(self, binding, no_delivery_evidence):
        return self._run('release', binding, evidence_ref=no_delivery_evidence)

    def reconcile(self, binding, delivered, evidence_ref):
        return self._run('reconcile', binding, delivered=delivered, evidence_ref=evidence_ref)

    def _run(self, operation, binding, *, delivered=None, evidence_ref=None):
        try:
            require(binding.environment == self.environment, ReasonCode.SOURCE_NOT_APPROVED)
            reference(binding.domain_ref, maximum=120)
            if operation in ('release', 'reconcile'):
                reference(evidence_ref)
            if operation == 'commit' or (operation == 'reconcile' and delivered is not None):
                count(delivered, binding.quantity)
            bound = content_hash({'binding': binding, 'window': self.window_key,
                                  'limit': self.limit, 'ttl_seconds': self.ttl_seconds})
            if evidence_ref is None:
                evidence_ref = 'quota/' + content_hash({'binding': bound, 'operation': operation,
                                                       'delivered': delivered})
            with transaction.atomic():
                created = False
                if operation == 'reserve':
                    record, created = QuotaExecution.objects.get_or_create(
                        idempotency_key=binding.idempotency_key,
                        defaults={'reservation_id': binding.reservation_id, 'binding_hash': bound})
                record = QuotaExecution.objects.select_for_update().filter(
                    idempotency_key=binding.idempotency_key).first()
                require(record is not None, ReasonCode.AUTHORIZATION_DENIED)
                require(record.binding_hash == bound, ReasonCode.IDEMPOTENCY_CONFLICT)
                if operation == 'reserve':
                    require(timezone.now() < binding.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
                    hold = QuotaService.reserve(subject_id=binding.subject_ref, data_domain=binding.domain_ref,
                        window_key=self.window_key, amount=binding.quantity,
                        request_fingerprint=binding.request_fingerprint, reservation_id=binding.reservation_id,
                        limit=self.limit, ttl_seconds=self.ttl_seconds)
                    # A pre-existing legacy hold has no full ExecutionBinding provenance.
                    require(not (created and hold.idempotent_replay), ReasonCode.IDEMPOTENCY_CONFLICT)
                state = QuotaService.observe(reservation_id=binding.reservation_id)
                require((state.subject_id, state.data_domain, state.window_key,
                         state.request_fingerprint, state.amount) ==
                        (binding.subject_ref, binding.domain_ref, self.window_key,
                         binding.request_fingerprint, binding.quantity), ReasonCode.IDEMPOTENCY_CONFLICT)
                if state.state in ('committed', 'released'):
                    require(record.terminal_receipt is not None and record.terminal_operation == operation,
                            ReasonCode.IDEMPOTENCY_CONFLICT)
                    receipt = QuotaReceipt.from_wire(record.terminal_receipt)
                    require(receipt.state.value == state.state and receipt.evidence_ref == evidence_ref
                            and receipt.settled_amount == delivered, ReasonCode.IDEMPOTENCY_CONFLICT)
                    if state.state == 'committed':
                        require(state.settled_amount == delivered, ReasonCode.IDEMPOTENCY_CONFLICT)
                    return receipt
                if operation in ('reserve', 'require_active', 'active_until', 'commit'):
                    active = QuotaService.require_active(reservation_id=binding.reservation_id,
                        request_fingerprint=binding.request_fingerprint, amount=binding.quantity)
                    # The binding deadline may be shorter than the quota service's TTL.
                    require(timezone.now() < binding.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
                    if operation == 'active_until':
                        return min(active.expires_at, binding.expires_at)
                if operation == 'commit':
                    QuotaService.commit(reservation_id=binding.reservation_id, delivered_amount=delivered)
                elif operation == 'release':
                    # The original service rejects release from unknown, even after expiry.
                    QuotaService.release(reservation_id=binding.reservation_id)
                elif operation == 'reconcile':
                    if state.state == 'unknown' and delivered is None and record.unknown_receipt is not None:
                        receipt = QuotaReceipt.from_wire(record.unknown_receipt)
                        require(receipt.evidence_ref == evidence_ref, ReasonCode.IDEMPOTENCY_CONFLICT)
                        return receipt
                    QuotaService.reconcile(reservation_id=binding.reservation_id, delivered_amount=delivered)
                state = QuotaService.observe(reservation_id=binding.reservation_id)
                receipt = QuotaReceipt(schema_version=QuotaReceipt.SCHEMA, binding=binding,
                    state=QuotaState(state.state), observed_at=timezone.now(), evidence_ref=evidence_ref,
                    settled_amount=state.settled_amount if state.state == 'committed' else None)
                if state.state in ('committed', 'released'):
                    record.terminal_operation = operation
                    record.terminal_receipt = receipt.to_wire()
                    record.save(update_fields=['terminal_operation', 'terminal_receipt'])
                elif state.state == 'unknown':
                    record.unknown_receipt = receipt.to_wire()
                    record.save(update_fields=['unknown_receipt'])
                return receipt
        except ContractViolation as error:
            code = error.code
        except (IntegrityError, QuotaConflict):
            code = ReasonCode.IDEMPOTENCY_CONFLICT
        except QuotaExceeded:
            code = ReasonCode.LIMIT_EXCEEDED
        except QuotaError:
            code = ReasonCode.AUTHORIZATION_DENIED
        except DatabaseError:
            # No automatic release on database uncertainty; the flow owns recovery.
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=binding.execution_id)
