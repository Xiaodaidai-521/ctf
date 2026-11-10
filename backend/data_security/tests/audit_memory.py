"""Single-threaded audit contract model, not a durable ledger or filesystem."""
from dataclasses import replace
import hashlib
import json

from data_security.contracts import (
    AuditCheckpoint, AuditReceipt, ContractViolation, Durability, Environment, KeyPurpose,
    KeyReference, KeyStatus, ProtectionError, QuotaRecoveryEvent, ReasonCode,
    SecurityEventV2, canonical_bytes, content_hash,
)
from data_security.contracts.schema import reference, require


class MemoryAuditSink:
    def __init__(self, *, records, entries, legacy, checkpoints, clock, crypto=None,
                 key=None, context=None, retained_keys=(), checkpoint_ref=None):
        require(all(v is None for v in (crypto, key, context)) or
                all(v is not None for v in (crypto, key, context)))
        self.records, self.entries, self.legacy = records, entries, legacy
        self.checkpoints, self.checkpoint_ref = checkpoints, checkpoint_ref
        self.clock, self.crypto, self.key = clock, crypto, key
        self.keys, self.context = {}, None
        if crypto is not None:
            require(context.environment in (Environment.TEST, Environment.EVALUATION),
                    ReasonCode.SOURCE_NOT_APPROVED)
            for ref in (key, *retained_keys):
                require(ref.purpose is KeyPurpose.AUDIT and
                        ref.status in (KeyStatus.ACTIVE, KeyStatus.READ_ONLY), ReasonCode.KEY_UNAVAILABLE)
                require(ref.key_ref not in self.keys)
                self.keys[ref.key_ref] = ref
            self.context = replace(context, field_ref='audit/ledger.v2')
            self.identity = content_hash(dict(project=context.project_ref,
                environment=context.environment, object=context.object_uuid,
                version=context.object_version, chain_version='ds.audit.v2'))

    def _content(self, entry, row):
        return dict(chain_version='ds.audit.v2', chain_identity=entry['chain_identity'],
            sequence=entry['sequence'], previous_hash=entry['previous_hash'],
            event_hash=entry['event_hash'], event_id=entry['event_id'],
            stored_at=row['stored_at'], recorded_at=entry['recorded_at'], key=entry['key'])

    def _checked(self, entry):
        row = self.records[entry['event_id']]
        event_type = {SecurityEventV2.SCHEMA: SecurityEventV2,
                      QuotaRecoveryEvent.SCHEMA: QuotaRecoveryEvent}[row['event']['schema_version']]
        event = event_type.from_wire(row['event'])
        require(event.to_wire() == row['event'] and event.event_id == entry['event_id'])
        require(entry['chain_identity'] == self.identity and
                event.occurred_at <= row['stored_at'] <= entry['recorded_at'])
        require(content_hash(event) == entry['event_hash'])
        signed = KeyReference.from_wire(entry['key'])
        current = self.keys[signed.key_ref]
        require(signed == replace(current, status=KeyStatus.ACTIVE))
        content = self._content(entry, row)
        require(self.crypto.verify_authentication(canonical_bytes(content), entry['authentication'],
                                                 self.context, current) is True)
        require(entry['current_hash'] == content_hash(dict(
            content=content, authentication=entry['authentication'])))
        return event

    def _receipt(self, entry):
        return AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=entry['event_id'],
            durability=Durability.LEDGER_CONFIRMED,
            stored_at=self.records[entry['event_id']]['stored_at'], chain_version='ds.audit.v2',
            entry_ref=entry['ref'], sequence=entry['sequence'], entry_hash=entry['current_hash'],
            checkpoint_ref=None)

    def append(self, event, durability):
        try:
            v2 = type(event) in (SecurityEventV2, QuotaRecoveryEvent)
            require(not v2 or self.crypto is not None)
            row = self.records.get(event.event_id)
            if row is not None and row['event'] != event.to_wire():
                return ProtectionError(schema_version=ProtectionError.SCHEMA,
                    code=ReasonCode.IDEMPOTENCY_CONFLICT, retryable=False,
                    trace_id=event.correlation_ref)
            if row is None:
                row = dict(event=event.to_wire(), stored_at=self.clock())
            receipt = AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=event.event_id,
                durability=Durability.DURABLE, stored_at=row['stored_at'], chain_version=None,
                entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
            if durability is Durability.LEDGER_CONFIRMED:
                if v2:
                    existing = next((e for e in self.entries if e['event_id'] == event.event_id), None)
                    if existing is not None:
                        self._checked(existing)
                        return self._receipt(existing)
                    require(self.key.status is KeyStatus.ACTIVE)
                    chain = [e for e in self.entries if e['chain_identity'] == self.identity]
                    tail = max(chain, key=lambda e: e['sequence']) if chain else None
                    if tail is not None:
                        self._checked(tail)
                    at = self.clock()
                    require(event.occurred_at <= row['stored_at'] <= at and
                            (tail is None or at >= tail['recorded_at']))
                    entry = dict(event_id=event.event_id, chain_identity=self.identity,
                        sequence=tail['sequence'] + 1 if tail else 1,
                        previous_hash=tail['current_hash'] if tail else '0' * 64,
                        event_hash=content_hash(event), recorded_at=at, key=self.key.to_wire(),
                        ref=f'audit/v2/{len(self.entries) + 1}')
                    content = self._content(entry, row)
                    authentication = self.crypto.authenticate(canonical_bytes(content), self.context, self.key)
                    require(type(authentication) is bytes and len(authentication) == 32)
                    entry['authentication'] = authentication
                    entry['current_hash'] = content_hash(dict(content=content, authentication=authentication))
                    # Nothing is published into shared state until signing succeeds.
                    self.records[event.event_id] = row
                    self.entries.append(entry)
                    return self._receipt(entry)
                entry = next((e for e in self.legacy if e['event_id'] == event.event_id), None)
                if entry is None:
                    content = dict(previous_hash=self.legacy[-1]['hash'] if self.legacy else '0' * 64,
                        payload_hash=content_hash(event), event_category=event.kind.value,
                        object_type='data_security.event', object_id=event.event_id,
                        actor_id=None, chain_version='v1')
                    entry = dict(event_id=event.event_id, payload=event.to_wire(), content=content,
                                 hash=content_hash(content), at=self.clock(), sequence=len(self.legacy) + 1)
                    self.legacy.append(entry)
                receipt = replace(receipt, durability=durability, chain_version='v1',
                    entry_ref=f'audit/ledger/{entry["sequence"]}', sequence=entry['sequence'],
                    entry_hash=entry['hash'])
            self.records[event.event_id] = row
            return receipt
        except (ContractViolation, KeyError, TypeError, ValueError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id=event.correlation_ref)

    def _checkpoint(self):
        if self.checkpoint_ref is None:
            return None
        encoded = self.checkpoints[self.checkpoint_ref]
        require(0 < len(encoded) <= 16384)
        point = AuditCheckpoint.from_json(encoded)
        require(canonical_bytes(point) == encoded and
                self.checkpoint_ref == 'audit/checkpoint/' + content_hash(point) and
                point.chain_identity == self.identity)
        current = self.keys[point.key.key_ref]
        require(point.key == replace(current, status=KeyStatus.ACTIVE))
        require(self.crypto.verify_authentication(canonical_bytes(point.content()), point.authentication,
            replace(self.context, field_ref='audit/checkpoint.v1'), current) is True)
        return point

    def _chain(self, point, *, event_id=None):
        tail, previous_hash, previous_time, sequence = None, '0' * 64, None, 0
        anchored = point is None
        matched = None
        for entry in sorted((e for e in self.entries if e['chain_identity'] == self.identity),
                            key=lambda e: e['sequence']):
            event = self._checked(entry)
            if event.event_id == event_id:
                matched = event
            require(entry['sequence'] == sequence + 1 and entry['previous_hash'] == previous_hash and
                    (previous_time is None or entry['recorded_at'] >= previous_time))
            if point is not None and entry['sequence'] == point.receipt.sequence:
                require(self._receipt(entry) == point.receipt and point.checkpointed_at >= entry['recorded_at'])
                anchored = True
            tail, previous_hash, previous_time, sequence = (
                entry, entry['current_hash'], entry['recorded_at'], entry['sequence'])
        require(tail is not None and anchored)
        return tail, matched

    def verify(self, chain_ref):
        if chain_ref not in ('v1', 'ds.audit.v2') or (chain_ref == 'ds.audit.v2' and self.crypto is None):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.UNSUPPORTED_FORMAT, retryable=False, trace_id='audit/verify')
        try:
            if chain_ref == 'ds.audit.v2':
                tail, _ = self._chain(self._checkpoint())
                return replace(self._receipt(tail), checkpoint_ref=self.checkpoint_ref)
            previous = '0' * 64
            require(bool(self.legacy))
            for entry in self.legacy:
                payload_hash = hashlib.sha256(json.dumps(entry['payload'], ensure_ascii=False,
                    sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
                require(payload_hash == entry['content']['payload_hash'] and
                        entry['content']['previous_hash'] == previous and
                        content_hash(entry['content']) == entry['hash'])
                previous = entry['hash']
            return AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=entry['event_id'],
                durability=Durability.LEDGER_CONFIRMED, stored_at=entry['at'], chain_version='v1',
                entry_ref=f'audit/ledger/{entry["sequence"]}', sequence=entry['sequence'],
                entry_hash=entry['hash'], checkpoint_ref=None)
        except (ContractViolation, KeyError, TypeError, ValueError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='audit/verify')

    def read_authenticated(self, event_id):
        if self.crypto is None:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.UNSUPPORTED_FORMAT, retryable=False, trace_id='audit/read')
        try:
            reference(event_id, maximum=64)
            _, event = self._chain(self._checkpoint(), event_id=event_id)
            require(event is not None)
            return event
        except (ContractViolation, KeyError, TypeError, ValueError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='audit/read')

    def checkpoint(self, chain_ref):
        if chain_ref != 'ds.audit.v2' or self.checkpoints is None:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.UNSUPPORTED_FORMAT, retryable=False, trace_id='audit/checkpoint')
        try:
            require(self.key.status is KeyStatus.ACTIVE)
            previous = self._checkpoint()
            tail, _ = self._chain(previous)
            at = self.clock()
            require(at >= tail['recorded_at'] and (previous is None or at >= previous.checkpointed_at))
            receipt = self._receipt(tail)
            values = dict(schema_version=AuditCheckpoint.SCHEMA, chain_identity=self.identity,
                          receipt=receipt, checkpointed_at=at, key=self.key)
            authentication = self.crypto.authenticate(canonical_bytes(values),
                replace(self.context, field_ref='audit/checkpoint.v1'), self.key)
            require(type(authentication) is bytes and len(authentication) == 32)
            point = AuditCheckpoint(**values, authentication=authentication)
            ref, encoded = 'audit/checkpoint/' + content_hash(point), canonical_bytes(point)
            require(len(encoded) <= 16384)
            require(ref not in self.checkpoints or self.checkpoints[ref] == encoded)
            self.checkpoints[ref] = encoded
            return replace(receipt, checkpoint_ref=ref)
        except (ContractViolation, KeyError, TypeError, ValueError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='audit/checkpoint')
