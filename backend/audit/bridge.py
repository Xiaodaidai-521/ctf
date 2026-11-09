"""Explicitly bound legacy entry points. Unbound callers retain the old behavior."""
from data_security.contracts import (AuditPort, AuditReceipt, ContractViolation, Durability,
    EventKind, Outcome, PolicyBinding, ProtectionError, ReasonCode, SecurityEvent)
from data_security.contracts.schema import require


_binding = None


def bind(*, audit: AuditPort, policy_binding: PolicyBinding, clock, event_id):
    """B supplies the sole gateway, fixed policy binding, UTC clock and ID source."""
    require(type(policy_binding) is PolicyBinding and callable(clock) and callable(event_id),
            ReasonCode.INVALID_TYPE)
    global _binding
    _binding = (audit, policy_binding, clock, event_id)


def is_bound():
    return _binding is not None


def record(*, category, actor_id=None, object_id=None, failed=False,
           durability=Durability.DURABLE):
    """Project only server IDs and fixed kinds; never accept original detail/text."""
    audit, policy_binding, clock, new_id = _binding
    kind = {
        'auth': EventKind.AUTHORIZATION,
        'consent_sign': EventKind.AUTHORIZATION,
        'risk_override': EventKind.AUTHORIZATION,
        'report_export': EventKind.DELIVERY,
    }.get(category, EventKind.PROTECTION)
    event = SecurityEvent(schema_version=SecurityEvent.SCHEMA,
        event_id=new_id(), kind=kind,
        actor_ref=f'user/{actor_id}' if type(actor_id) is int and actor_id > 0 else 'actor/unspecified',
        object_ref=f'legacy/{object_id}' if type(object_id) is int and object_id > 0 else 'legacy/event',
        object_version='legacy-v1', outcome=Outcome.FAILED if failed else Outcome.UNKNOWN,
        occurred_at=clock(), counts=(), policy_binding=policy_binding,
        algorithm_versions=(), key_versions=(), correlation_ref='audit/legacy',
        reason=ReasonCode.AUDIT_UNAVAILABLE if failed else None)
    receipt = audit.record(event, durability)
    if type(receipt) is ProtectionError:
        raise ContractViolation(receipt.code)
    require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id
            and receipt.durability is durability, ReasonCode.AUDIT_UNAVAILABLE)
    return receipt
