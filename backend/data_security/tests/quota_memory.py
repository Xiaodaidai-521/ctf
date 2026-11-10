"""Single-threaded QuotaPort test implementation; no database or transaction claims."""
from datetime import timedelta

from data_security.contracts import (
    ContractViolation, ProtectionError, QuotaReceipt, QuotaState, ReasonCode, content_hash,
)
from data_security.contracts.schema import count, reference, require


class MemoryQuotaPort:
    def __init__(self, *, records, bucket_limits, clock, environment, window_key, limit, ttl_seconds=300):
        require(environment in ('test', 'evaluation'), ReasonCode.SOURCE_NOT_APPROVED)
        reference(window_key, maximum=80)
        count(limit, 2**53 - 1)
        count(ttl_seconds, 86400)
        require(ttl_seconds > 0)
        self.records, self.bucket_limits, self.clock = records, bucket_limits, clock
        self.environment, self.window_key = environment, window_key
        self.limit, self.ttl_seconds = limit, ttl_seconds

    def reserve(self, binding):
        return self._run('reserve', binding)

    def require_active(self, binding):
        return self._run('require_active', binding)

    def read_committed(self, binding):
        try:
            require(binding.environment == self.environment, ReasonCode.SOURCE_NOT_APPROVED)
            reference(binding.domain_ref, maximum=120)
            bound = content_hash({'binding': binding, 'window': self.window_key,
                                  'limit': self.limit, 'ttl_seconds': self.ttl_seconds})
            record = self.records.get(binding.idempotency_key)
            require(record is not None, ReasonCode.AUTHORIZATION_DENIED)
            require(record['bound'] == bound, ReasonCode.IDEMPOTENCY_CONFLICT)
            state = record['receipt']
            require(state.binding == binding and record['bucket'] ==
                    (binding.subject_ref, binding.domain_ref, self.window_key), ReasonCode.IDEMPOTENCY_CONFLICT)
            require(state.state is QuotaState.COMMITTED, ReasonCode.AUTHORIZATION_DENIED)
            require(record.get('terminal_receipt') is not None
                    and record['terminal_operation'] in ('commit', 'reconcile'), ReasonCode.IDEMPOTENCY_CONFLICT)
            receipt = QuotaReceipt.from_wire(record['terminal_receipt'])
            require(receipt.binding == binding and receipt.state is QuotaState.COMMITTED
                    and receipt.settled_amount == state.settled_amount, ReasonCode.IDEMPOTENCY_CONFLICT)
            if record['terminal_operation'] == 'commit':
                evidence = 'quota/' + content_hash({'binding': bound, 'operation': 'commit',
                                                   'delivered': state.settled_amount})
                require(receipt.evidence_ref == evidence, ReasonCode.IDEMPOTENCY_CONFLICT)
            return receipt
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=binding.execution_id)

    def active_until(self, binding):
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
            now = self.clock()
            record = self.records.get(binding.idempotency_key)
            if record is not None:
                require(record['bound'] == bound, ReasonCode.IDEMPOTENCY_CONFLICT)
            if operation == 'reserve':
                require(now < binding.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
                if record is None:
                    require(all(r['receipt'].binding.reservation_id != binding.reservation_id
                                for r in self.records.values()), ReasonCode.IDEMPOTENCY_CONFLICT)
                    bucket = (binding.subject_ref, binding.domain_ref, self.window_key)
                    used = sum(r['receipt'].held_amount + (r['receipt'].settled_amount or 0)
                               for r in self.records.values() if r['bucket'] == bucket)
                    limit = self.bucket_limits.get(bucket, self.limit)
                    require(used + binding.quantity <= limit, ReasonCode.LIMIT_EXCEEDED)
                    receipt = QuotaReceipt(schema_version=QuotaReceipt.SCHEMA, binding=binding,
                        state=QuotaState.RESERVED, settled_amount=None, observed_at=now, evidence_ref=evidence_ref)
                    self.records[binding.idempotency_key] = {
                        'bound': bound, 'bucket': bucket, 'expires_at': now + timedelta(seconds=self.ttl_seconds),
                        'receipt': receipt, 'terminal_operation': None,
                    }
                    self.bucket_limits.setdefault(bucket, limit)
                    return receipt
                require(record['receipt'].state is QuotaState.RESERVED
                        and now < record['expires_at'], ReasonCode.AUTHORIZATION_DENIED)
            require(record is not None, ReasonCode.AUTHORIZATION_DENIED)
            previous = record['receipt']
            if previous.state in (QuotaState.COMMITTED, QuotaState.RELEASED):
                require(record['terminal_operation'] == operation
                        and previous.evidence_ref == evidence_ref and previous.settled_amount == delivered,
                        ReasonCode.IDEMPOTENCY_CONFLICT)
                return previous
            if operation in ('reserve', 'require_active', 'active_until', 'commit'):
                require(previous.state is QuotaState.RESERVED and now < record['expires_at'],
                        ReasonCode.AUTHORIZATION_DENIED)
                require(now < binding.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
                if operation == 'active_until':
                    return min(record['expires_at'], binding.expires_at)
            state = previous.state
            if operation == 'release':
                require(state is QuotaState.RESERVED, ReasonCode.AUTHORIZATION_DENIED)
                state = QuotaState.RELEASED
            elif operation == 'commit' or (operation == 'reconcile' and delivered is not None):
                state = QuotaState.COMMITTED
            elif operation == 'reconcile':
                if state is QuotaState.UNKNOWN:
                    require(previous.evidence_ref == evidence_ref, ReasonCode.IDEMPOTENCY_CONFLICT)
                    return previous
                state = QuotaState.UNKNOWN
            receipt = QuotaReceipt(schema_version=QuotaReceipt.SCHEMA, binding=binding, state=state,
                settled_amount=delivered if state is QuotaState.COMMITTED else None,
                observed_at=now, evidence_ref=evidence_ref)
            record['receipt'] = receipt
            if state in (QuotaState.COMMITTED, QuotaState.RELEASED):
                record['terminal_operation'] = operation
                record['terminal_receipt'] = receipt.to_wire()
            return receipt
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=binding.execution_id)
