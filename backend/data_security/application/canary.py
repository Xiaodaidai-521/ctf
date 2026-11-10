"""Agent-callable canary operations with explicit synthetic owners and catalog.

No production target, background scan, generic sensitive-data detector or ledger
writer lives here. Target persistence and trusted authorization are injected.
"""
from dataclasses import replace
import re

from data_security.contracts import (
    AuditReceipt, BoundedPayload, CanarySeed, ContractViolation, Durability,
    Environment, EventKind, FrozenJSON, Limits, MediaType, Outcome, Outlet, PayloadKind,
    PolicyBinding, ProtectionContext, ProtectionError, Purpose, ReasonCode, SecurityEventV2, TableSnapshot,
)
from data_security.contracts.schema import require


class CanaryTools:
    def __init__(self, *, seeds, environment, domain, limits, policy_binding,
                 authorize, plant_target, audit, clock, event_id):
        require(type(environment) is Environment and environment in
                (Environment.TEST, Environment.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
        require(type(limits) is Limits and type(policy_binding) is PolicyBinding, ReasonCode.INVALID_TYPE)
        require(type(seeds) is tuple and all(type(seed) is CanarySeed for seed in seeds), ReasonCode.INVALID_TYPE)
        require(0 < len(seeds) <= limits.max_findings, ReasonCode.LIMIT_EXCEEDED)
        require(len({seed.seed_id for seed in seeds}) == len(seeds))
        require(all(seed.environment is environment and seed.domain == domain for seed in seeds),
                ReasonCode.SOURCE_NOT_APPROVED)
        self.environment, self.domain, self.limits = environment, domain, limits
        self.policy_binding, self.authorize, self.plant_target = policy_binding, authorize, plant_target
        self.audit, self.clock, self.event_id = audit, clock, event_id
        self.catalog = {}
        for seed in seeds:
            number = int(seed.seed_id, 16)
            subnet, host = divmod(number % 762, 254)
            # A non-routable 000000 prefix, not a real issuer or payment credential.
            body = '0000001' + f'{number % 100_000_000:08d}'
            total = sum((2 * int(c) - 9 if int(c) >= 5 else 2 * int(c)) if i % 2 == 0 else int(c)
                        for i, c in enumerate(body))
            values = {
                'email_address': seed.seed_id + '@example.invalid',
                'ip_address': ('192.0.2.', '198.51.100.', '203.0.113.')[subnet] + str(host + 1),
                'payment_card_candidate': body + str((-total) % 10),
            }
            boundaries = (r"A-Za-z0-9.!#$%&'*+/=?^_`{|}~-", r'0-9A-Za-z_.', r'0-9A-Za-z')
            patterns = tuple(re.compile(r'(?<![' + left + '])' + re.escape(value) +
                r'(?![' + (r'A-Za-z0-9.-' if category == 'email_address' else left) + '])')
                for (category, value), left in zip(values.items(), boundaries))
            packet = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.JSON,
                media_type=MediaType.JSON, text=None, binary=None, limits=limits,
                tree=FrozenJSON({'schema_version': 'ds.synthetic-canary.v1', 'synthetic': True,
                    'seed': seed.to_wire(), 'values': values}))
            self.catalog[seed.seed_id] = (seed, packet, patterns)
        self.tools = {'canary.plant': self.plant, 'canary.check': self.check}

    def plant(self, *, seed_id, context):
        """The target owner must atomically persist packet and registration, or fail."""
        try:
            require(type(context) is ProtectionContext, ReasonCode.INVALID_TYPE)
            require(context.environment is self.environment and context.domain == self.domain and
                    context.outlet is Outlet.AUDIT and context.purpose is Purpose.SECURITY_AUDIT,
                    ReasonCode.AUTHORIZATION_DENIED)
            require(type(seed_id) is str and seed_id in self.catalog, ReasonCode.SOURCE_NOT_APPROVED)
            seed, packet, _ = self.catalog[seed_id]
            require((context.object_ref, context.object_version) == (seed.target_ref, seed.target_version),
                    ReasonCode.AUTHORIZATION_DENIED)
            authorized = self.authorize('canary.plant', context, seed)
            if type(authorized) is ProtectionError:
                return authorized
            require(type(authorized) is ProtectionContext and authorized == context, ReasonCode.AUTHORIZATION_DENIED)
            result = self.plant_target(seed, packet, context)
            if type(result) is ProtectionError:
                return result
            require(type(result) is CanarySeed and result == seed, ReasonCode.SOURCE_NOT_APPROVED)
            return seed
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id='canary/plant')

    def check(self, *, payload, context):
        """Return confirmed alerts, or an error; an empty tuple means no exact hit.

        Check decoded TEXT/JSON or an actual output TableSnapshot, not compressed
        or encrypted bytes. Sheet titles are checked separately by the owner.
        A matching TEST-NET address identifies possible sources, not a
        globally unique source: every registered match gets its own event.
        """
        try:
            require(type(context) is ProtectionContext and type(payload) in (BoundedPayload, TableSnapshot),
                    ReasonCode.INVALID_TYPE)
            require(context.environment is self.environment and context.domain == self.domain and
                    context.outlet in (Outlet.MODEL, Outlet.EMBEDDING, Outlet.LOG, Outlet.EXPORT),
                    ReasonCode.AUTHORIZATION_DENIED)
            if type(payload) is BoundedPayload:
                require(payload.kind in (PayloadKind.TEXT, PayloadKind.JSON), ReasonCode.UNSUPPORTED_FORMAT)
            else:
                require(context.outlet is Outlet.EXPORT, ReasonCode.UNSUPPORTED_SCOPE)
            # Reconstruct once at this boundary with this tool's explicit limits.
            payload = replace(payload, limits=self.limits)
            authorized = self.authorize('canary.check', context, None)
            if type(authorized) is ProtectionError:
                return authorized
            require(type(authorized) is ProtectionContext and authorized == context, ReasonCode.AUTHORIZATION_DENIED)
            texts = []
            def collect(value):
                if type(value) is dict:
                    for key, child in value.items():
                        texts.append(key)
                        collect(child)
                elif type(value) is list:
                    for child in value:
                        collect(child)
                elif type(value) is str:
                    texts.append(value)
            if type(payload) is TableSnapshot:
                texts.extend(cell.original_text for cell in payload.cells)
                texts.extend(column.label for column in payload.columns)
            else:
                collect(payload.text if payload.kind is PayloadKind.TEXT else payload.tree.to_value())
            receipts = []
            for seed, _, patterns in self.catalog.values():
                hits = sum(any(pattern.search(text) for text in texts) for pattern in patterns)
                if not hits:
                    continue
                event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                    event_id=self.event_id(), kind=EventKind.PROTECTION, actor_ref=context.actor_ref,
                    object_ref=seed.target_ref, object_version=seed.target_version,
                    outcome=Outcome.FAILED, occurred_at=self.clock(), counts=(('hit', hits),),
                    policy_binding=self.policy_binding,
                    algorithm_versions=('canary-exact-v1', 'seed/' + seed.seed_id,
                                        'target/' + seed.target_kind, 'outlet/' + context.outlet.value),
                    key_versions=(), correlation_ref=context.trace_id, reason=ReasonCode.MATCHED_FORMAT,
                    evidence_hashes=())
                receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
                if type(receipt) is ProtectionError:
                    return receipt
                require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                        receipt.durability is Durability.LEDGER_CONFIRMED and
                        receipt.chain_version == 'ds.audit.v2' and receipt.stored_at >= event.occurred_at,
                        ReasonCode.AUDIT_UNAVAILABLE)
                receipts.append(receipt)
            return tuple(receipts)
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id='canary/check')
