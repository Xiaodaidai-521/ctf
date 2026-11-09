"""Synthetic-only phase-2 ports. Never imported by production modules."""
from dataclasses import replace
from datetime import timedelta
import hashlib

from data_security.contracts import *
from data_security.tests.fixtures import AT, HASH, approval, dto, examples


def text(value, limits=BASELINE_LIMITS):
    return dto(BoundedPayload, kind=PayloadKind.TEXT, media_type=MediaType.TEXT,
               text=value, tree=None, binary=None, limits=limits)


def tree(value, limits=BASELINE_LIMITS):
    return dto(BoundedPayload, kind=PayloadKind.JSON, media_type=MediaType.JSON,
               text=None, tree=FrozenJSON(value), binary=None, limits=limits)


def algorithm(name=Algorithm.REPLACE, **kwargs):
    values = dict(algorithm=name, version='v1', replacement=None, keep_prefix=None,
        keep_suffix=None, mask_symbol=None, max_length=None, ipv4_prefix=None,
        pseudonym_bits=None, key_ref=None)
    if name is Algorithm.REPLACE:
        values['replacement'] = Replacement.REDACTED
    values.update(kwargs)
    return dto(AlgorithmSpec, **values)


def context(**kwargs):
    return replace(examples()[ProtectionContext], scope_refs=('content/body',), outlet=Outlet.API,
                   purpose=Purpose.DISPLAY, **kwargs)


def policy(ctx=None, specs=None, exceptions=()):
    ctx = ctx or context()
    specs = specs or {category: algorithm() for category in Category}
    rules = tuple(dto(PolicyRule, category=c, outlet=ctx.outlet, role=ctx.role,
                      purpose=ctx.purpose, action=a) for c, a in specs.items())
    values = dict(schema_version=PolicySnapshot.SCHEMA, version='phase2-fixture-v1', rules=rules,
        teaching_exceptions=exceptions, effective_at=AT, expires_at=AT + timedelta(hours=1))
    digest = content_hash(values)
    snapshot = PolicySnapshot(**values, status=PolicyStatus.APPROVED, content_hash=digest, approval=approval(digest))
    binding = dto(PolicyBinding, protection_version=snapshot.version, protection_hash=digest,
                  risk_version='risk-fixture-v1', risk_hash=HASH, contract_version=CONTRACT_VERSION)
    return snapshot, binding


def action(category=Category.EMAIL, spec=None, *, start=0, end=5, path=(), kind=None, number=0):
    kind = kind or (LocationKind.JSON_FIELD if path else LocationKind.TEXT_SPAN)
    loc = dto(Location, kind=kind, sheet_id=None, source_row=None, column_id=None,
              start=None if path else start, end=None if path else end, json_path=path)
    return dto(ResolvedAction, action_id=f'action/{number}', source_operation_ref=f'finding/{number}',
        location=loc, category=category, algorithm=spec or algorithm(), finding_refs=(), requirement_refs=())


def root_key(label='data'):
    return hashlib.sha256(('never-activated-phase2-fixture:' + label).encode()).digest()


def reference_key(purpose=KeyPurpose.DATA, status=KeyStatus.ACTIVE):
    return dto(KeyReference, purpose=purpose, key_ref=purpose.value + '/v1', version='v1', status=status)


class MemoryPolicy:
    def __init__(self, snapshot):
        self.value = snapshot
        self.calls = []

    def read(self, binding):
        self.calls.append(binding)
        if (binding.protection_version, binding.protection_hash) != (self.value.version, self.value.content_hash):
            return dto(ProtectionError, code=ReasonCode.POLICY_NOT_APPROVED, retryable=False, trace_id='fixture/policy')
        return self.value

    def snapshot(self, binding):
        return self.read(binding)

    def approve(self, snapshot, approval, context):
        return dto(ProtectionError, code=ReasonCode.AUTHORIZATION_DENIED, retryable=False, trace_id='fixture/policy')

    def retire(self, binding, context):
        return dto(ProtectionError, code=ReasonCode.AUTHORIZATION_DENIED, retryable=False, trace_id='fixture/policy')

    def put(self, snapshot, expected_version):
        if expected_version != self.value.version:
            return dto(ProtectionError, code=ReasonCode.IDEMPOTENCY_CONFLICT, retryable=False, trace_id='fixture/policy')
        self.value = snapshot
        return True


class FakeKeys:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def resolve(self, key_ref, purpose, service_identity):
        self.calls.append((key_ref, purpose, service_identity))
        if self.error:
            return dto(ProtectionError, code=self.error, retryable=False, trace_id='fixture/keys')
        if key_ref.purpose is not purpose or key_ref.status is KeyStatus.RETIRED:
            return dto(ProtectionError, code=ReasonCode.KEY_UNAVAILABLE, retryable=False, trace_id='fixture/keys')
        return SecretMaterial(root_key(purpose.value), purpose)


class MemoryAudit:
    def __init__(self, reject=False):
        self.reject = reject
        self.events = []

    def append(self, event, durability):
        self.events.append(event)
        if self.reject or durability is not Durability.DURABLE:
            return dto(ProtectionError, code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='fixture/audit')
        return dto(AuditReceipt, event_id=event.event_id, durability=durability, stored_at=AT,
                   chain_version=None, entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)

    def record(self, event, durability):
        return self.append(event, durability)

    def verify(self, chain_ref):
        return dto(ProtectionError, code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='fixture/audit')

    def checkpoint(self, chain_ref):
        return self.verify(chain_ref)
