"""One audit sink, with separate legacy and purpose-authenticated chain versions."""
from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from django.core.management.color import no_style
from django.db import DatabaseError, connection, transaction

from audit.models import (AuditEvent, AuditLedgerEntry, AuditLedgerLock, AuthenticatedAuditEntry,
                          SecurityAuditRecord)
from audit.services import AuditLedgerService
from data_security.contracts import (AuditCheckpoint, AuditReceipt, AuditSink, ContractViolation, Durability,
    Environment, FrozenJSON, KeyPurpose, KeyReference, KeyStatus, ObjectContext, ProtectionError,
    QuotaRecoveryEvent, ReasonCode, SecurityEvent, SecurityEventV2, canonical_bytes, content_hash)
from data_security.contracts.schema import count, digest, reference, require, utc


class DjangoAuditSink(AuditSink):
    def __init__(self, *, clock, crypto=None, key=None, context=None, retained_keys=(),
                 checkpoint_root=None, checkpoint_ref=None):
        self.clock, self.crypto = clock, crypto
        require(all(v is None for v in (crypto, key, context)) or
                all(v is not None for v in (crypto, key, context)))
        self.key, self.context, self.keys = key, None, {}
        if crypto is not None:
            require(type(context) is ObjectContext and context.environment in
                    (Environment.TEST, Environment.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
            for ref in (key, *retained_keys):
                require(type(ref) is KeyReference and ref.purpose is KeyPurpose.AUDIT and
                        ref.status in (KeyStatus.ACTIVE, KeyStatus.READ_ONLY), ReasonCode.KEY_UNAVAILABLE)
                require(ref.key_ref not in self.keys)
                self.keys[ref.key_ref] = ref
            self.context = replace(context, field_ref='audit/ledger.v2')
            # Stable identity excludes the renewable operator authorization reference.
            self.chain_identity = content_hash({'project': context.project_ref,
                'environment': context.environment, 'object': context.object_uuid,
                'version': context.object_version, 'chain_version': 'ds.audit.v2'})
        self.checkpoint_root, self.checkpoint_ref = None, checkpoint_ref
        if checkpoint_root is not None:
            require(crypto is not None, ReasonCode.KEY_UNAVAILABLE)
            root = Path(checkpoint_root)
            require(root.is_absolute() and root.resolve(strict=True) == root,
                    ReasonCode.AUTHORIZATION_DENIED)
            info = root.stat()
            require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700 and
                    info.st_uid == os.geteuid(), ReasonCode.AUTHORIZATION_DENIED)
            self.checkpoint_root = root
        if checkpoint_ref is not None:
            require(self.checkpoint_root is not None and type(checkpoint_ref) is str and
                    checkpoint_ref.startswith('audit/checkpoint/'), ReasonCode.AUTHORIZATION_DENIED)
            digest(checkpoint_ref.removeprefix('audit/checkpoint/'))

    def append(self, event: SecurityEvent | SecurityEventV2 | QuotaRecoveryEvent,
               durability: Durability) -> AuditReceipt | ProtectionError:
        # No gateway, protection facade, outbox or recursive audit on this path.
        try:
            if type(event) in (SecurityEventV2, QuotaRecoveryEvent):
                require(self.crypto is not None, ReasonCode.AUDIT_UNAVAILABLE)
            with transaction.atomic():
                wire = event.to_wire()
                row, _ = SecurityAuditRecord.objects.get_or_create(
                    event_id=event.event_id,
                    defaults={'event': wire, 'stored_at': self.clock(),
                        # A validated metadata-only SecurityEvent is already protected.
                        # Bypass the business write hook so auditing does not audit itself.
                        'audit_event': lambda: AuditEvent._base_manager.bulk_create([AuditEvent(
                            category='data_processing', level='INFO', security_state='sealed-v1',
                            security_revision=1, summary=event.kind.value, detail=wire)])[0]},
                )
                # Keep event-row -> ledger-singleton -> ledger-tail lock order.
                row = SecurityAuditRecord.objects.select_for_update().get(pk=row.pk)
                if row.event != wire:
                    return ProtectionError(schema_version=ProtectionError.SCHEMA,
                        code=ReasonCode.IDEMPOTENCY_CONFLICT, retryable=False,
                        trace_id=event.correlation_ref)
                entry = None
                if durability is Durability.LEDGER_CONFIRMED:
                    if type(event) in (SecurityEventV2, QuotaRecoveryEvent):
                        return self._append_v2(row, event)
                    if row.ledger_entry_id is None:
                        row.ledger_entry = AuditLedgerService._append_entry(
                            event_category=event.kind.value, payload=wire,
                            object_type='data_security.event', object_id=event.event_id,
                            chain_version='v1')
                        row.save(update_fields=['ledger_entry'])
                    entry = row.ledger_entry
                return AuditReceipt(schema_version=AuditReceipt.SCHEMA,
                    event_id=event.event_id, durability=durability, stored_at=row.stored_at,
                    chain_version=entry.chain_version if entry else None,
                    entry_ref=f'audit/ledger/{entry.pk}' if entry else None,
                    sequence=entry.pk if entry else None,
                    entry_hash=entry.current_hash if entry else None, checkpoint_ref=None)
        except (DatabaseError, ContractViolation, KeyError, TypeError, ValueError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id=event.correlation_ref)

    def _entry_content(self, entry):
        return {'chain_version': 'ds.audit.v2', 'chain_identity': entry.chain_identity,
            'sequence': entry.sequence, 'previous_hash': entry.previous_hash,
            'event_hash': entry.event_hash, 'event_id': entry.record.event_id,
            'stored_at': entry.record.stored_at, 'recorded_at': entry.recorded_at,
            'key': entry.key}

    def _checked_entry(self, entry):
        """The database is a boundary, not an authority for keys or evidence."""
        event_type = {SecurityEventV2.SCHEMA: SecurityEventV2,
                      QuotaRecoveryEvent.SCHEMA: QuotaRecoveryEvent}.get(entry.record.event['schema_version'])
        require(event_type is not None, ReasonCode.AUDIT_UNAVAILABLE)
        event = event_type.from_wire(entry.record.event)
        require(event.to_wire() == entry.record.event and event.event_id == entry.record.event_id,
                ReasonCode.AUDIT_UNAVAILABLE)
        require(entry.record.ledger_entry_id is None and entry.chain_identity == self.chain_identity,
                ReasonCode.AUDIT_UNAVAILABLE)
        count(entry.sequence, 2**53 - 1)
        require(entry.sequence > 0)
        for value in (entry.previous_hash, entry.event_hash, entry.current_hash):
            digest(value)
        utc(entry.record.stored_at)
        utc(entry.recorded_at)
        require(event.occurred_at <= entry.record.stored_at <= entry.recorded_at,
                ReasonCode.AUDIT_UNAVAILABLE)
        require(entry.event_hash == content_hash(event), ReasonCode.AUDIT_UNAVAILABLE)
        signed_key = KeyReference.from_wire(entry.key)
        current_key = self.keys.get(signed_key.key_ref)
        require(current_key is not None and signed_key == replace(current_key, status=KeyStatus.ACTIVE),
                ReasonCode.KEY_UNAVAILABLE)
        authentication = bytes(entry.authentication)
        require(len(authentication) == 32, ReasonCode.AUDIT_UNAVAILABLE)
        content = self._entry_content(entry)
        verified = self.crypto.verify_authentication(canonical_bytes(content), authentication,
                                                      self.context, current_key)
        require(verified is True, ReasonCode.AUDIT_UNAVAILABLE)
        require(entry.current_hash == content_hash({'content': content, 'authentication': authentication}),
                ReasonCode.AUDIT_UNAVAILABLE)
        return event

    def _receipt_v2(self, entry):
        return AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=entry.record.event_id,
            durability=Durability.LEDGER_CONFIRMED, stored_at=entry.record.stored_at,
            chain_version='ds.audit.v2', entry_ref=f'audit/v2/{entry.pk}', sequence=entry.sequence,
            entry_hash=entry.current_hash, checkpoint_ref=None)

    def _append_v2(self, row, event):
        # Called only after append() has locked the durable event, in its transaction.
        lock = 'v2:' + self.chain_identity[:40]
        AuditLedgerLock.objects.get_or_create(key=lock)
        AuditLedgerLock.objects.select_for_update().get(key=lock)
        previous = AuthenticatedAuditEntry.objects.select_related('record').filter(record=row).first()
        if previous is not None:
            self._checked_entry(previous)
            return self._receipt_v2(previous)
        require(self.key.status is KeyStatus.ACTIVE, ReasonCode.KEY_UNAVAILABLE)
        tail = AuthenticatedAuditEntry.objects.select_related('record').filter(
            chain_identity=self.chain_identity).order_by('-sequence').first()
        if tail is not None:
            self._checked_entry(tail)
        at = self.clock()
        utc(at)
        require(event.occurred_at <= row.stored_at <= at and
                (tail is None or at >= tail.recorded_at), ReasonCode.AUDIT_UNAVAILABLE)
        entry = AuthenticatedAuditEntry(record=row, chain_identity=self.chain_identity,
            sequence=tail.sequence + 1 if tail else 1, previous_hash=tail.current_hash if tail else '0' * 64,
            event_hash=content_hash(event), recorded_at=at, key=self.key.to_wire())
        count(entry.sequence, 2**53 - 1)
        content = self._entry_content(entry)
        authentication = self.crypto.authenticate(canonical_bytes(content), self.context, self.key)
        require(type(authentication) is bytes and len(authentication) == 32, ReasonCode.AUDIT_UNAVAILABLE)
        entry.authentication = authentication
        entry.current_hash = content_hash({'content': content, 'authentication': authentication})
        entry.save(force_insert=True)
        return self._receipt_v2(entry)

    def _checkpoint_bytes(self, path):
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and
                    info.st_uid == os.geteuid() and 0 < info.st_size <= 16384,
                    ReasonCode.AUDIT_UNAVAILABLE)
            encoded = stream.read(16385)
        require(len(encoded) <= 16384, ReasonCode.LIMIT_EXCEEDED)
        return encoded

    def _load_checkpoint(self, checkpoint_ref=None):
        chosen = self.checkpoint_ref if checkpoint_ref is None else checkpoint_ref
        if chosen is None:
            return None
        require(type(chosen) is str and chosen.startswith('audit/checkpoint/'), ReasonCode.AUDIT_UNAVAILABLE)
        name = chosen.removeprefix('audit/checkpoint/')
        digest(name)
        try:
            encoded = self._checkpoint_bytes(self.checkpoint_root / (name + '.json'))
        except OSError:
            raise ContractViolation(ReasonCode.AUDIT_UNAVAILABLE) from None
        checkpoint = AuditCheckpoint.from_json(encoded)
        require(canonical_bytes(checkpoint) == encoded and content_hash(checkpoint) == name and
                checkpoint.chain_identity == self.chain_identity, ReasonCode.AUDIT_UNAVAILABLE)
        current_key = self.keys.get(checkpoint.key.key_ref)
        require(current_key is not None and checkpoint.key == replace(current_key, status=KeyStatus.ACTIVE),
                ReasonCode.KEY_UNAVAILABLE)
        verified = self.crypto.verify_authentication(canonical_bytes(checkpoint.content()),
            checkpoint.authentication, replace(self.context, field_ref='audit/checkpoint.v1'), current_key)
        require(verified is True, ReasonCode.AUDIT_UNAVAILABLE)
        return checkpoint

    def _locked_chain(self, checkpoint, *, event_id=None, recovery_events=None, recovery_keys=None):
        # Recovery supplies a PostgreSQL read-only snapshot instead of taking online locks.
        if recovery_events is None:
            lock = 'v2:' + self.chain_identity[:40]
            AuditLedgerLock.objects.get_or_create(key=lock)
            AuditLedgerLock.objects.select_for_update().get(key=lock)
        previous_hash, sequence, previous_time, tail = '0' * 64, 0, None, None
        anchored = checkpoint is None
        matched = None
        for entry in AuthenticatedAuditEntry.objects.select_related('record').filter(
                chain_identity=self.chain_identity).order_by('sequence').iterator(chunk_size=256):
            event = self._checked_entry(entry)
            if recovery_events is not None:
                recovery_events[event.event_id] = event, self._receipt_v2(entry)
                recovery_keys.add(entry.key['key_ref'])
            if event.event_id == event_id:
                matched = event
            require(entry.sequence == sequence + 1 and entry.previous_hash == previous_hash and
                    (previous_time is None or entry.recorded_at >= previous_time),
                    ReasonCode.AUDIT_UNAVAILABLE)
            if checkpoint is not None and entry.sequence == checkpoint.receipt.sequence:
                require(self._receipt_v2(entry) == checkpoint.receipt and
                        checkpoint.checkpointed_at >= entry.recorded_at, ReasonCode.AUDIT_UNAVAILABLE)
                anchored = True
            previous_hash, sequence, previous_time, tail = (
                entry.current_hash, entry.sequence, entry.recorded_at, entry)
        require(tail is not None and anchored, ReasonCode.AUDIT_UNAVAILABLE)
        return tail, matched

    def inspect_recovery(self, limits):
        """Internal to the isolated verifier's read-only transaction; never creates an anchor."""
        require(connection.vendor == 'postgresql' and connection.in_atomic_block and self.crypto is not None,
                ReasonCode.SOURCE_NOT_APPROVED)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('transaction_read_only')")
            require(cursor.fetchone()[0] == 'on', ReasonCode.SOURCE_NOT_APPROVED)
        require(AuthenticatedAuditEntry.objects.filter(chain_identity=self.chain_identity).count()
                <= limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
        checkpoint = self._load_checkpoint()
        require(checkpoint is not None, ReasonCode.AUDIT_UNAVAILABLE)
        events, keys = {}, {checkpoint.key.key_ref}
        tail, _ = self._locked_chain(checkpoint, recovery_events=events, recovery_keys=keys)
        return {'tail': self._receipt_v2(tail), 'checkpoint': checkpoint, 'events': events, 'key_refs': sorted(keys)}

    def _verify_v2(self):
        try:
            checkpoint = self._load_checkpoint()
            with transaction.atomic():
                tail, _ = self._locked_chain(checkpoint)
                return replace(self._receipt_v2(tail), checkpoint_ref=self.checkpoint_ref)
        except (DatabaseError, ContractViolation, OSError, KeyError, TypeError, ValueError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='audit/verify')

    def verify(self, chain_ref: str) -> AuditReceipt | ProtectionError:
        if chain_ref == 'ds.audit.v2' and self.crypto is not None:
            return self._verify_v2()
        if chain_ref != 'v1':
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.UNSUPPORTED_FORMAT, retryable=False, trace_id='audit/verify')
        try:
            # Serialize against the same append lock while choosing the verified tail.
            with transaction.atomic():
                AuditLedgerLock.objects.get_or_create(key='default')
                AuditLedgerLock.objects.select_for_update().get(key='default')
                valid = AuditLedgerService.verify_chain().is_valid
                entry = AuditLedgerEntry.objects.order_by('-id').first()
                if not valid or entry is None or entry.chain_version != 'v1':
                    return ProtectionError(schema_version=ProtectionError.SCHEMA,
                        code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='audit/verify')
                row = SecurityAuditRecord.objects.filter(ledger_entry=entry).first()
                return AuditReceipt(schema_version=AuditReceipt.SCHEMA,
                    event_id=row.event_id if row else f'legacy/{entry.pk}',
                    durability=Durability.LEDGER_CONFIRMED, stored_at=entry.created_at,
                    chain_version='v1', entry_ref=f'audit/ledger/{entry.pk}', sequence=entry.pk,
                    entry_hash=entry.current_hash, checkpoint_ref=None)
        except (DatabaseError, ContractViolation):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='audit/verify')

    def read_authenticated(self, event_id: str) -> SecurityEventV2 | QuotaRecoveryEvent | ProtectionError:
        """Read metadata from the verified configured chain, not from a raw event-row lookup."""
        if self.crypto is None:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.UNSUPPORTED_FORMAT, retryable=False, trace_id='audit/read')
        try:
            reference(event_id, maximum=64)
            checkpoint = self._load_checkpoint()
            with transaction.atomic():
                _, event = self._locked_chain(checkpoint, event_id=event_id)
                require(event is not None, ReasonCode.AUDIT_UNAVAILABLE)
                return event
        except (DatabaseError, ContractViolation, OSError, KeyError, TypeError, ValueError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='audit/read')

    def _recovery_entry(self, entry):
        return {'entry_id': entry.pk, 'event': entry.record.event,
            'stored_at': entry.record.stored_at.isoformat(), 'sequence': entry.sequence,
            'previous_hash': entry.previous_hash, 'event_hash': entry.event_hash,
            'recorded_at': entry.recorded_at.isoformat(), 'key': entry.key,
            'authentication': bytes(entry.authentication).hex(), 'current_hash': entry.current_hash}

    def capture_recovery(self, limits):
        """Bounded metadata mirror of an original checkpoint, never a replacement chain."""
        try:
            require(self.crypto is not None and self.checkpoint_root is not None
                    and not connection.in_atomic_block, ReasonCode.AUTHORIZATION_DENIED)
            require(AuthenticatedAuditEntry.objects.filter(chain_identity=self.chain_identity).count()
                    <= limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
            receipt = self.checkpoint('ds.audit.v2')
            if isinstance(receipt, ProtectionError):
                return receipt
            checkpoint = self._load_checkpoint(receipt.checkpoint_ref)
            with transaction.atomic():
                self._locked_chain(checkpoint)
                entries = [self._recovery_entry(entry) for entry in
                    AuthenticatedAuditEntry.objects.select_related('record').filter(
                        chain_identity=self.chain_identity, sequence__lte=receipt.sequence).order_by('sequence')]
            require(len(entries) <= limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
            document = {'schema_version': 'ds.audit-recovery.v1', 'checkpoint_ref': receipt.checkpoint_ref,
                'chain_identity': self.chain_identity, 'entries': entries, 'key': self.key.to_wire()}
            encoded = json.dumps(document, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=False, allow_nan=False).encode('utf-8')
            require(len(encoded) <= limits.max_json_bytes, ReasonCode.LIMIT_EXCEEDED)
            # The mirror MAC also binds database entry IDs, which are receipt identities
            # but are not fields of the original per-entry authentication content.
            authentication = self.crypto.authenticate(encoded,
                replace(self.context, field_ref='audit/recovery.v1'), self.key)
            require(type(authentication) is bytes and len(authentication) == 32, ReasonCode.AUDIT_UNAVAILABLE)
            return FrozenJSON({**document, 'authentication': authentication.hex()},
                              max_bytes=limits.max_json_bytes)
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError, KeyError, TypeError, ValueError):
            code = ReasonCode.AUDIT_UNAVAILABLE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='audit/capture-recovery')

    def _checked_recovery(self, bundle, limits):
        """Shared file boundary for a mirror and the original closed-gate restore."""
        require(type(bundle) is FrozenJSON, ReasonCode.INVALID_TYPE)
        document = bundle.to_value()
        require(type(document) is dict and set(document) == {
            'schema_version', 'checkpoint_ref', 'chain_identity', 'entries', 'key', 'authentication'},
            ReasonCode.UNKNOWN_FIELD)
        require(document['schema_version'] == 'ds.audit-recovery.v1'
                and document['chain_identity'] == self.chain_identity, ReasonCode.AUDIT_UNAVAILABLE)
        authentication = bytes.fromhex(document.pop('authentication'))
        require(len(authentication) == 32, ReasonCode.AUDIT_UNAVAILABLE)
        signed_key = KeyReference.from_wire(document['key'])
        current_key = self.keys.get(signed_key.key_ref)
        require(current_key is not None and signed_key == replace(current_key, status=KeyStatus.ACTIVE),
                ReasonCode.KEY_UNAVAILABLE)
        encoded = json.dumps(document, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')
        require(len(encoded) <= limits.max_json_bytes, ReasonCode.LIMIT_EXCEEDED)
        require(self.crypto.verify_authentication(encoded, authentication,
            replace(self.context, field_ref='audit/recovery.v1'), current_key) is True,
            ReasonCode.AUDIT_UNAVAILABLE)
        # The original retained file must still exist. Restore never manufactures an anchor.
        checkpoint = self._load_checkpoint(document['checkpoint_ref'])
        require(type(document['entries']) is list and 0 < len(document['entries']) <= limits.max_actions,
                ReasonCode.LIMIT_EXCEEDED)
        entries, previous_hash, previous_time = [], '0' * 64, None
        for sequence, value in enumerate(document['entries'], 1):
            require(type(value) is dict and set(value) == {
                'entry_id', 'event', 'stored_at', 'sequence', 'previous_hash', 'event_hash',
                'recorded_at', 'key', 'authentication', 'current_hash'}, ReasonCode.UNKNOWN_FIELD)
            count(value['entry_id'], 2**53 - 1)
            require(value['entry_id'] > 0, ReasonCode.AUDIT_UNAVAILABLE)
            row = SecurityAuditRecord(event_id=value['event']['event_id'], event=value['event'],
                                      stored_at=datetime.fromisoformat(value['stored_at']))
            entry = AuthenticatedAuditEntry(pk=value['entry_id'], record=row,
                chain_identity=self.chain_identity, sequence=value['sequence'],
                previous_hash=value['previous_hash'], event_hash=value['event_hash'],
                recorded_at=datetime.fromisoformat(value['recorded_at']), key=value['key'],
                authentication=bytes.fromhex(value['authentication']), current_hash=value['current_hash'])
            event = self._checked_entry(entry)
            require(entry.sequence == sequence and entry.previous_hash == previous_hash
                    and (previous_time is None or entry.recorded_at >= previous_time),
                    ReasonCode.AUDIT_UNAVAILABLE)
            entries.append((entry, event))
            previous_hash, previous_time = entry.current_hash, entry.recorded_at
        require(self._receipt_v2(entries[-1][0]) == checkpoint.receipt
                and checkpoint.checkpointed_at >= previous_time, ReasonCode.AUDIT_UNAVAILABLE)
        return checkpoint, entries

    def verify_recovery(self, bundle, limits):
        """Verify an already-present prefix without appending or replacing ledger entries."""
        try:
            require(self.crypto is not None and self.checkpoint_root is not None,
                    ReasonCode.SOURCE_NOT_APPROVED)
            checkpoint, entries = self._checked_recovery(bundle, limits)
            require(AuthenticatedAuditEntry.objects.filter(chain_identity=self.chain_identity).count()
                    <= limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
            with transaction.atomic():
                tail, _ = self._locked_chain(self._load_checkpoint() or checkpoint)
                current = list(AuthenticatedAuditEntry.objects.select_related('record').filter(
                    chain_identity=self.chain_identity, sequence__lte=checkpoint.receipt.sequence).order_by('sequence'))
                require(len(current) == len(entries) and all(
                    self._recovery_entry(existing) == self._recovery_entry(expected)
                    for existing, (expected, _) in zip(current, entries)), ReasonCode.AUDIT_UNAVAILABLE)
            return replace(self._receipt_v2(tail), checkpoint_ref=bundle.to_value()['checkpoint_ref'])
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError, KeyError, TypeError, ValueError):
            code = ReasonCode.AUDIT_UNAVAILABLE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='audit/verify-recovery')

    def restore_recovery(self, bundle, limits, context, *, journal):
        """Append an authenticated missing suffix while the original recovery gate is closed."""
        try:
            require(connection.vendor == 'postgresql' and not connection.in_atomic_block
                    and self.crypto is not None and self.checkpoint_root is not None,
                    ReasonCode.SOURCE_NOT_APPROVED)
            state = journal.read(context)
            require(state['state'] == 'restored' and state['environment'] == self.context.environment.value,
                    ReasonCode.SOURCE_NOT_APPROVED)
            checkpoint, entries = self._checked_recovery(bundle, limits)
            selected = self._load_checkpoint()
            if selected is not None:
                require(selected.receipt.sequence <= len(entries)
                        and self._receipt_v2(entries[selected.receipt.sequence - 1][0]) == selected.receipt
                        and checkpoint.checkpointed_at >= selected.checkpointed_at, ReasonCode.AUDIT_UNAVAILABLE)
            with transaction.atomic():
                lock = 'v2:' + self.chain_identity[:40]
                AuditLedgerLock.objects.get_or_create(key=lock)
                AuditLedgerLock.objects.select_for_update().get(key=lock)
                current = list(AuthenticatedAuditEntry.objects.select_related('record').filter(
                    chain_identity=self.chain_identity).order_by('sequence')[:limits.max_actions + 1])
                require(len(current) <= len(entries), ReasonCode.AUDIT_UNAVAILABLE)
                for existing, (expected, _) in zip(current, entries):
                    require(existing.record.ledger_entry_id is None
                            and self._recovery_entry(existing) == self._recovery_entry(expected),
                            ReasonCode.AUDIT_UNAVAILABLE)
                for entry, event in entries[len(current):]:
                    row, _ = SecurityAuditRecord.objects.get_or_create(event_id=event.event_id,
                        defaults={'event': entry.record.event, 'stored_at': entry.record.stored_at,
                            'audit_event': lambda: AuditEvent._base_manager.bulk_create([AuditEvent(
                                category='data_processing', level='INFO', security_state='sealed-v1',
                                security_revision=1, summary=event.kind.value, detail=entry.record.event)])[0]})
                    require(row.event == entry.record.event and row.stored_at == entry.record.stored_at
                            and row.ledger_entry_id is None, ReasonCode.AUDIT_UNAVAILABLE)
                    entry.record = row
                    entry.save(force_insert=True)
                if len(current) < len(entries):
                    with connection.cursor() as cursor:
                        for statement in connection.ops.sequence_reset_sql(no_style(), [AuthenticatedAuditEntry]):
                            cursor.execute(statement)
            return replace(checkpoint.receipt, checkpoint_ref=bundle.to_value()['checkpoint_ref'])
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError, KeyError, TypeError, ValueError):
            code = ReasonCode.AUDIT_UNAVAILABLE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='audit/restore-recovery')

    def checkpoint(self, chain_ref: str) -> AuditReceipt | ProtectionError:
        if chain_ref != 'ds.audit.v2' or self.checkpoint_root is None:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.UNSUPPORTED_FORMAT, retryable=False, trace_id='audit/checkpoint')
        try:
            # A file must never anchor entries visible only in an outer transaction.
            require(not connection.in_atomic_block, ReasonCode.AUTHORIZATION_DENIED)
            require(self.key.status is KeyStatus.ACTIVE, ReasonCode.KEY_UNAVAILABLE)
            previous = self._load_checkpoint()
            with transaction.atomic():
                tail, _ = self._locked_chain(previous)
                at = self.clock()
                utc(at)
                require(at >= tail.recorded_at and
                        (previous is None or at >= previous.checkpointed_at), ReasonCode.AUDIT_UNAVAILABLE)
                receipt = self._receipt_v2(tail)
                values = dict(schema_version=AuditCheckpoint.SCHEMA, chain_identity=self.chain_identity,
                    receipt=receipt, checkpointed_at=at, key=self.key)
                authentication = self.crypto.authenticate(canonical_bytes(values),
                    replace(self.context, field_ref='audit/checkpoint.v1'), self.key)
                require(type(authentication) is bytes and len(authentication) == 32,
                        ReasonCode.AUDIT_UNAVAILABLE)
                checkpoint = AuditCheckpoint(**values, authentication=authentication)
                encoded = canonical_bytes(checkpoint)
                require(len(encoded) <= 16384, ReasonCode.LIMIT_EXCEEDED)
                name = content_hash(checkpoint)
                path = self.checkpoint_root / (name + '.json')
                try:
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                except FileExistsError:
                    require(self._checkpoint_bytes(path) == encoded, ReasonCode.AUDIT_UNAVAILABLE)
                else:
                    # Immutable object; no reference is returned before both fsyncs.
                    # A failed write is retained, never silently overwritten or trusted.
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(encoded)
                        stream.flush()
                        os.fsync(stream.fileno())
                directory = os.open(self.checkpoint_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            return replace(receipt, checkpoint_ref='audit/checkpoint/' + name)
        except (DatabaseError, ContractViolation, OSError, KeyError, TypeError, ValueError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUDIT_UNAVAILABLE, retryable=False, trace_id='audit/checkpoint')
