"""Single audit entry point; never calls the auditing protection facade."""
from data_security.contracts import (AuditPort, AuditReceipt, AuditSink, Durability,
                                     ProtectionError, QuotaRecoveryEvent, ReasonCode, SecurityEvent, SecurityEventV2)


class AuditGateway(AuditPort):
    def __init__(self, *, sink: AuditSink):
        self.sink = sink

    def record(self, event: SecurityEvent | SecurityEventV2 | QuotaRecoveryEvent, durability: Durability) -> AuditReceipt | ProtectionError:
        # DTO construction is the field whitelist. Do not accept dictionaries,
        # detail, exception objects, or ORM records at this boundary.
        if type(event) not in (SecurityEvent, SecurityEventV2, QuotaRecoveryEvent) or type(durability) is not Durability:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.INVALID_TYPE, retryable=False, trace_id='audit/gateway')
        try:
            receipt = self.sink.append(event, durability)
        except Exception:
            # No logging or callback into this gateway: a failing sink gets one attempt.
            receipt = None
        if type(receipt) is ProtectionError:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=receipt.code, retryable=receipt.retryable, trace_id=event.correlation_ref)
        if (type(receipt) is not AuditReceipt or receipt.event_id != event.event_id
                or receipt.durability is not durability or receipt.stored_at < event.occurred_at):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id=event.correlation_ref)
        return receipt
