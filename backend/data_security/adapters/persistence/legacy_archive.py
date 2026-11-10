"""Isolated v1 archival and explicit source governance; never writes a second audit chain."""
from contextlib import suppress
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from uuid import uuid4

from django.db import DatabaseError, connection, transaction
from django.db.models import Q

from audit.models import AuditLedgerEntry, AuditLedgerLock, SecurityAuditRecord
from audit.services import AuditLedgerService
from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, Environment, EventKind, KeyPurpose, Outcome, ProtectionError,
    Purpose, ReasonCode, Role, SecurityEventV2, StoredObject, content_hash,
)
from data_security.contracts.schema import count, digest, reference, require


class DjangoLegacyAuditArchive:
    def __init__(self, *, directory, age, keys, service_identity, environment, domain,
                 policy_binding, limits, clock):
        require(environment in (Environment.TEST, Environment.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
        root = Path(directory)
        require(root.is_absolute() and root.resolve(strict=True) == root, ReasonCode.SOURCE_NOT_APPROVED)
        info = root.stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o700, ReasonCode.SOURCE_NOT_APPROVED)
        self.directory, self.age, self.keys = root, str(age), keys
        self.service_identity, self.environment, self.domain = service_identity, environment, domain
        self.policy_binding, self.limits, self.clock = policy_binding, limits, clock

    def _registration(self, object_id):
        path = self.directory / (object_id + '.legacy.json')
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600, ReasonCode.SOURCE_NOT_APPROVED)
            raw = source.read(self.limits.max_json_bytes + 1)
        require(len(raw) <= self.limits.max_json_bytes, ReasonCode.LIMIT_EXCEEDED)
        value = json.loads(raw)
        require(type(value) is dict, ReasonCode.INVALID_VALUE)
        return value

    def _maintenance(self, context, *, recovery=False):
        require(context.actor_ref == self.service_identity and context.role is Role.SERVICE
                and context.purpose is Purpose.STORAGE and context.environment is self.environment
                and context.domain == self.domain, ReasonCode.AUTHORIZATION_DENIED)
        if recovery:
            require(connection.vendor == 'postgresql' and connection.in_atomic_block, ReasonCode.SOURCE_NOT_APPROVED)
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('transaction_read_only')")
                require(cursor.fetchone()[0] == 'on', ReasonCode.SOURCE_NOT_APPROVED)
        else:
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)

    def load(self, archive_ref, context, *, recovery=False):
        """Validate retained metadata and exact ciphertext; this is not approval or decryption."""
        try:
            self._maintenance(context, recovery=recovery)
            require(type(archive_ref) is str and re.fullmatch(r'audit/archive/[0-9a-f]{32}', archive_ref),
                    ReasonCode.INVALID_VALUE)
            object_id = archive_ref.split('/')[-1]
            metadata = self._registration(object_id)
            stored = StoredObject.from_wire(metadata['stored'])
            event = SecurityEventV2.from_wire(metadata['bridge_event'])
            reference(metadata['approval_ref'], maximum=64)
            require(metadata['bridge_state'] in ('pending', 'confirmed')
                    and metadata['format'] == stored.version == 'ds.legacy-audit-archive.v1'
                    and metadata['archive_ref'] == stored.object_ref == event.object_ref == archive_ref
                    and metadata['environment'] == self.environment.value and metadata['domain'] == self.domain
                    and metadata['chain_version'] == 'v1' and stored.state == 'verified'
                    and metadata['legacy_timestamps_authenticated'] is False
                    and metadata['security_records_authenticated'] is False
                    and event.event_id == 'archive/' + object_id and event.kind is EventKind.BACKUP
                    and event.outcome is Outcome.SUCCEEDED and event.actor_ref == self.service_identity
                    and event.object_version == stored.version and event.reason is None
                    and event.correlation_ref == metadata['approval_ref']
                    and event.policy_binding == self.policy_binding
                    and event.counts == (('records', metadata['chain_length']),
                                         ('processed', metadata['security_records']))
                    and event.evidence_hashes == (('archive', stored.ciphertext_hash),
                                                  ('report', metadata['tail_hash'])), ReasonCode.REPORT_MISMATCH)
            with os.fdopen(os.open(self.directory / (object_id + '.legacy.age'),
                                   os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
                info = os.fstat(source.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                        and stat.S_IMODE(info.st_mode) == 0o600, ReasonCode.SOURCE_NOT_APPROVED)
                require(info.st_size == stored.size_bytes
                        and hashlib.file_digest(source, 'sha256').hexdigest() == stored.ciphertext_hash,
                        ReasonCode.CIPHERTEXT_INVALID)
            return stored, event, metadata['approval_ref']
        except ContractViolation as error:
            code = error.code
        except (OSError, DatabaseError, ValueError, KeyError, TypeError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=context.trace_id)

    def verify_content(self, stored, event, identity, context, *, with_source=False):
        """Offline age/v1 check; optional whole-source digest, never rows or a restore grant."""
        process, key_fd = None, None
        source_hash = hashlib.sha256()
        try:
            require(context.actor_ref == self.service_identity and context.role is Role.SERVICE
                    and context.purpose is Purpose.STORAGE and context.environment is self.environment
                    and context.domain == self.domain, ReasonCode.AUTHORIZATION_DENIED)
            require(re.fullmatch(r'audit/archive/[0-9a-f]{32}', stored.object_ref)
                    and stored.version == 'ds.legacy-audit-archive.v1' and stored.state == 'verified'
                    and event.kind is EventKind.BACKUP and event.outcome is Outcome.SUCCEEDED
                    and event.object_ref == stored.object_ref and event.object_version == stored.version
                    and event.event_id == 'archive/' + stored.object_ref.split('/')[-1]
                    and event.actor_ref == self.service_identity and event.reason is None
                    and event.algorithm_versions == ('legacy/v1', 'age/v1')
                    and event.policy_binding == self.policy_binding, ReasonCode.REPORT_MISMATCH)
            expected = dict(event.counts)
            hashes = dict(event.evidence_hashes)
            require(hashes.get('archive') == stored.ciphertext_hash, ReasonCode.REPORT_MISMATCH)
            digest(hashes['report'])
            count(expected['records'], self.limits.max_actions)
            count(expected['processed'], self.limits.max_actions)
            require(expected['records'] > 0, ReasonCode.REPORT_MISMATCH)
            material = self.keys.resolve(identity, KeyPurpose.BACKUP_PRIVATE, self.service_identity)
            if isinstance(material, ProtectionError):
                return material
            private = bytes(material.borrow(KeyPurpose.BACKUP_PRIVATE)).strip()
            require(re.fullmatch(rb'AGE-SECRET-KEY-1[0-9A-Z]{58}', private), ReasonCode.KEY_UNAVAILABLE)
            object_id = stored.object_ref.split('/')[-1]
            with os.fdopen(os.open(self.directory / (object_id + '.legacy.age'),
                                   os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
                info = os.fstat(source.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                        and stat.S_IMODE(info.st_mode) == 0o600, ReasonCode.SOURCE_NOT_APPROVED)
                require(info.st_size == stored.size_bytes
                        and hashlib.file_digest(source, 'sha256').hexdigest() == stored.ciphertext_hash,
                        ReasonCode.CIPHERTEXT_INVALID)
                source.seek(0)
                key_fd = os.memfd_create('legacy-archive-identity', os.MFD_CLOEXEC)
                os.write(key_fd, private + b'\n')
                os.lseek(key_fd, 0, os.SEEK_SET)
                process = subprocess.Popen([self.age, '--decrypt', '--identity', f'/proc/self/fd/{key_fd}'],
                    stdin=source, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, pass_fds=(key_fd,))
                raw = process.stdout.readline(self.limits.max_json_bytes + 1)
                require(bool(raw), ReasonCode.CIPHERTEXT_INVALID)
                require(len(raw) <= self.limits.max_json_bytes, ReasonCode.LIMIT_EXCEEDED)
                header = json.loads(raw)
                require(type(header) is dict and header['format'] == stored.version
                        and header['archive_ref'] == stored.object_ref
                        and header['approval_ref'] == event.correlation_ref
                        and header['environment'] == self.environment.value and header['domain'] == self.domain
                        and header['chain_version'] == 'v1' and type(header['tail_id']) is int
                        and type(header['chain_length']) is int and header['chain_length'] == expected['records']
                        and type(header['security_records']) is int and header['security_records'] == expected['processed']
                        and header['tail_hash'] == hashes['report']
                        and header['legacy_timestamps_authenticated'] is False
                        and header['security_records_authenticated'] is False, ReasonCode.REPORT_MISMATCH)
                ledger_ids = set()
                fields = {field.attname for field in AuditLedgerEntry._meta.concrete_fields}

                def entries():
                    previous_id = 0
                    for index in range(expected['records']):
                        raw = process.stdout.readline(self.limits.max_bytes + 1)
                        require(len(raw) <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
                        value = json.loads(raw)
                        require(type(value) is dict and value['kind'] == 'ledger'
                                and type(value['row']) is dict and set(value['row']) == fields,
                                ReasonCode.REPORT_MISMATCH)
                        row = value['row']
                        require(type(row['id']) is int and row['id'] > previous_id
                                and row['chain_version'] == 'v1', ReasonCode.REPORT_MISMATCH)
                        previous_id = row['id']
                        ledger_ids.add(row['id'])
                        if with_source:
                            source_hash.update(json.dumps({'kind': 'ledger', 'row': row},
                                ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                                default=str).encode('utf-8') + b'\n')
                        if index == expected['records'] - 1:
                            require(row['id'] == header['tail_id'] and row['current_hash'] == hashes['report'],
                                    ReasonCode.REPORT_MISMATCH)
                        yield AuditLedgerEntry(**row)

                checked = AuditLedgerService.verify_chain(entries=entries())
                require(checked.is_valid and checked.checked_count == expected['records'],
                        ReasonCode.AUDIT_UNAVAILABLE)
                fields = {field.attname for field in SecurityAuditRecord._meta.concrete_fields}
                previous_id = 0
                for _ in range(expected['processed']):
                    raw = process.stdout.readline(self.limits.max_bytes + 1)
                    require(len(raw) <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
                    value = json.loads(raw)
                    require(type(value) is dict and value['kind'] == 'security-record'
                            and type(value['row']) is dict and set(value['row']) == fields,
                            ReasonCode.REPORT_MISMATCH)
                    row = value['row']
                    require(type(row['id']) is int and row['id'] > previous_id
                            and (row['ledger_entry_id'] in ledger_ids or
                                 (row['ledger_entry_id'] is None and type(row['event']) is dict
                                  and row['event'].get('schema_version') == 'ds.security-event.v1')),
                            ReasonCode.REPORT_MISMATCH)
                    previous_id = row['id']
                    if with_source:
                        source_hash.update(json.dumps({'kind': 'security-record', 'row': row},
                            ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                            default=str).encode('utf-8') + b'\n')
                require(process.stdout.read(1) == b'', ReasonCode.REPORT_MISMATCH)
                require(process.wait() == 0, ReasonCode.CIPHERTEXT_INVALID)
            # The digest includes raw event bodies and old timestamps only as captured
            # bytes; it does not upgrade their historical authentication guarantee.
            if with_source:
                return stored, dict(records=expected['records'], security_records=expected['processed'],
                    tail_id=header['tail_id'], tail_hash=hashes['report'], content_hash=source_hash.hexdigest())
            return stored
        except ContractViolation as error:
            code = error.code
        except (ValueError, KeyError, TypeError, RecursionError):
            code = ReasonCode.REPORT_MISMATCH
        except OSError:
            code = ReasonCode.DELIVERY_UNKNOWN
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                process.wait()
                process.stdout.close()
            if key_fd is not None:
                os.close(key_fd)
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=stored.object_ref)

    def read_governance(self, context, *, recovery=False):
        """Decode retained source metadata; the flow must authenticate every returned event."""
        try:
            self._maintenance(context, recovery=recovery)
            row = AuditLedgerLock.objects.filter(key='default').values('legacy_archive').first()
            if row is None or row['legacy_archive'] == {}:
                return None
            metadata = row['legacy_archive']
            require(type(metadata) is dict and set(metadata) == {'format', 'stored', 'source', 'state', 'operations'}
                    and metadata['format'] == 'ds.legacy-audit-source.v1', ReasonCode.REPORT_MISMATCH)
            stored = StoredObject.from_wire(metadata['stored'])
            require(re.fullmatch(r'audit/archive/[0-9a-f]{32}', stored.object_ref)
                    and stored.version == 'ds.legacy-audit-archive.v1' and stored.state == 'verified',
                    ReasonCode.REPORT_MISMATCH)
            source = metadata['source']
            require(type(source) is dict and set(source) ==
                    {'records', 'security_records', 'tail_id', 'tail_hash', 'content_hash'}, ReasonCode.REPORT_MISMATCH)
            count(source['records'], self.limits.max_actions)
            count(source['security_records'], self.limits.max_actions)
            count(source['tail_id'], 2**63 - 1)
            require(source['records'] > 0 and source['tail_id'] > 0, ReasonCode.REPORT_MISMATCH)
            digest(source['tail_hash'])
            digest(source['content_hash'])
            operations = metadata['operations']
            expected = {'quarantined': {'quarantine'}, 'deleted': {'quarantine', 'delete'}}
            require(metadata['state'] in expected and type(operations) is dict
                    and set(operations) == expected[metadata['state']], ReasonCode.REPORT_MISMATCH)
            decoded = {}
            for operation, values in operations.items():
                require(type(values) is dict and set(values) ==
                        {'event', 'receipt', 'bridge', 'checkpoint', 'recovery'}, ReasonCode.REPORT_MISMATCH)
                event = SecurityEventV2.from_wire(values['event'])
                receipt, bridge, checkpoint, recovery = (
                    AuditReceipt.from_wire(values[name]) for name in ('receipt', 'bridge', 'checkpoint', 'recovery'))
                require(all(value.chain_version == 'ds.audit.v2' and value.durability is Durability.LEDGER_CONFIRMED
                            for value in (receipt, bridge, checkpoint))
                        and recovery.durability is Durability.DURABLE and recovery.chain_version is None
                        and checkpoint.checkpoint_ref is not None and checkpoint.sequence >= bridge.sequence
                        and (checkpoint.sequence != bridge.sequence or
                             replace(checkpoint, checkpoint_ref=None) == bridge)
                        and bridge.event_id == 'archive/' + stored.object_ref.split('/')[-1]
                        and receipt.event_id == event.event_id and receipt.stored_at >= event.occurred_at,
                        ReasonCode.REPORT_MISMATCH)
                proof = dict(operation=operation, source=source, bridge=values['bridge'],
                             checkpoint=values['checkpoint'], recovery=values['recovery'])
                require(event.event_id == operation + '/' + stored.object_ref.split('/')[-1]
                        and event.kind is EventKind.PROTECTION and event.outcome is Outcome.SUCCEEDED
                        and event.object_ref == 'audit/legacy-v1'
                        and event.object_version == ('v1/quarantined' if operation == 'quarantine' else 'v1/deleted')
                        and event.correlation_ref == stored.object_ref and event.reason is None
                        and event.policy_binding == self.policy_binding
                        and event.algorithm_versions == ('legacy/v1', 'age/v1', 'legacy-source/v1')
                        and event.counts == (('records', source['records']), ('processed', source['security_records']))
                        and event.evidence_hashes == (('archive', stored.ciphertext_hash), ('report', content_hash(proof))),
                        ReasonCode.REPORT_MISMATCH)
                decoded[operation] = event, receipt
            return metadata, decoded
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, ValueError, KeyError, TypeError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=context.trace_id)

    def govern(self, *, stored, source, operation, event, bridge, checkpoint, recovery, previous, record, context,
               completed=None):
        """Whole-source change plus the injected Gateway event in one database commit.

        All age, recovery and checkpoint checks are completed by the flow beforehand.
        The default lock is also held by both supported v1 append paths. No file I/O,
        decryption, cross-domain SET_NULL or second ledger writer runs in this block.
        """
        try:
            self._maintenance(context)
            with transaction.atomic():
                AuditLedgerLock.objects.get_or_create(key='default')
                lock = AuditLedgerLock.objects.select_for_update().get(key='default')
                require(lock.legacy_archive == (previous if previous is not None else {}),
                        ReasonCode.IDEMPOTENCY_CONFLICT)
                require((completed is not None and previous is not None and operation in previous['operations']) or
                        (operation == 'quarantine' and previous is None) or
                        (operation == 'delete' and previous is not None and previous['state'] == 'quarantined'),
                        ReasonCode.SOURCE_NOT_APPROVED)
                deleted = previous is not None and previous['state'] == 'deleted'
                # These are the only governed tables. Bound JSON rows before materializing
                # them, then compare every captured column (including the unauthenticated
                # historical time/event fields), not just the old chain's count and tail.
                with connection.cursor() as cursor:
                    for table, expected_count in (('audit_auditledgerentry', 0 if deleted else source['records']),
                                                  ('audit_securityauditrecord', 0 if deleted else source['security_records'])):
                        where = ('' if table == 'audit_auditledgerentry' else
                            " WHERE ledger_entry_id IS NOT NULL OR event->>'schema_version'='ds.security-event.v1'")
                        cursor.execute('SELECT count(*), COALESCE(max(octet_length(row_to_json(t)::text)),0) '
                                       'FROM ' + table + ' t' + where)
                        rows, largest = cursor.fetchone()
                        require(rows == expected_count, ReasonCode.REPORT_MISMATCH)
                        require(rows <= self.limits.max_actions and largest <= self.limits.max_json_bytes,
                                ReasonCode.LIMIT_EXCEEDED)
                entries = AuditLedgerEntry._base_manager.order_by('id')
                records = SecurityAuditRecord._base_manager.filter(
                    Q(ledger_entry__isnull=False) | Q(event__schema_version='ds.security-event.v1')).order_by('id')
                source_hash = hashlib.sha256()
                for kind, rows in (('ledger', entries), ('security-record', records)):
                    for row in rows.values().iterator(chunk_size=1):
                        encoded = json.dumps({'kind': kind, 'row': row}, ensure_ascii=False, sort_keys=True,
                                             separators=(',', ':'), default=str).encode('utf-8') + b'\n'
                        require(len(encoded) <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
                        source_hash.update(encoded)
                require(source_hash.hexdigest() == (hashlib.sha256().hexdigest() if deleted else source['content_hash']),
                        ReasonCode.REPORT_MISMATCH)
                if completed is not None:
                    # Authentication happened outside the lock. Recheck the actual source
                    # state as well; a retained success marker alone is not a safe replay.
                    return stored, completed
                if operation == 'delete':
                    # Deliberately bypass Django's deletion collector: legal SET_NULL
                    # relations must block at their database FK, never be rewritten here.
                    with connection.cursor() as cursor:
                        cursor.execute("DELETE FROM audit_securityauditrecord WHERE ledger_entry_id IS NOT NULL "
                                       "OR event->>'schema_version'='ds.security-event.v1'")
                        require(cursor.rowcount == source['security_records'], ReasonCode.REPORT_MISMATCH)
                        cursor.execute('DELETE FROM audit_auditledgerentry')
                        require(cursor.rowcount == source['records'], ReasonCode.REPORT_MISMATCH)
                receipt = record(event, Durability.LEDGER_CONFIRMED)
                if isinstance(receipt, ProtectionError):
                    raise ContractViolation(receipt.code)
                require(type(receipt) is AuditReceipt and receipt.chain_version == 'ds.audit.v2'
                        and receipt.durability is Durability.LEDGER_CONFIRMED and receipt.event_id == event.event_id,
                        ReasonCode.AUDIT_UNAVAILABLE)
                operations = dict(previous['operations']) if previous is not None else {}
                operations[operation] = dict(event=event.to_wire(), receipt=receipt.to_wire(), bridge=bridge.to_wire(),
                                             checkpoint=checkpoint.to_wire(), recovery=recovery.to_wire())
                lock.legacy_archive = dict(format='ds.legacy-audit-source.v1', stored=stored.to_wire(), source=source,
                    state='quarantined' if operation == 'quarantine' else 'deleted', operations=operations)
                lock.save(update_fields=['legacy_archive', 'updated_at'])
            return stored, receipt
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            # Includes deferred FK rejection and lost COMMIT acknowledgement. Never
            # erase the existing quarantine record or infer absence of a committed effect.
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=stored.object_ref)

    def confirm(self, stored, event, receipt, context):
        """Persist the Gateway receipt after its commit; a sidecar never authorizes a retry."""
        try:
            self._maintenance(context)
            require(re.fullmatch(r'audit/archive/[0-9a-f]{32}', stored.object_ref), ReasonCode.INVALID_VALUE)
            object_id = stored.object_ref.split('/')[-1]
            metadata = self._registration(object_id)
            require(metadata['stored'] == stored.to_wire() and metadata['bridge_event'] == event.to_wire(),
                    ReasonCode.REPORT_MISMATCH)
            metadata.update(bridge_state='confirmed', bridge_receipt=receipt.to_wire())
            temporary = self.directory / (object_id + '.bridge-' + uuid4().hex + '.partial')
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
                json.dump(metadata, output, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(self.directory / (object_id + '.legacy.json'))
            directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return receipt
        except ContractViolation as error:
            code = error.code
        except (OSError, DatabaseError, ValueError, KeyError, TypeError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=stored.object_ref)

    def create(self, *, expected_count, expected_tail, recipient, context):
        """The upstream owner must authorize this exact old-chain count/tail before calling."""
        process, key_fd = None, None
        object_id = uuid4().hex
        archive_ref = 'audit/archive/' + object_id
        partial = self.directory / (object_id + '.legacy.partial')
        final = self.directory / (object_id + '.legacy.age')
        try:
            require(context.actor_ref == self.service_identity and context.role is Role.SERVICE
                    and context.purpose is Purpose.STORAGE and context.environment is self.environment
                    and context.domain == self.domain, ReasonCode.AUTHORIZATION_DENIED)
            require(connection.get_autocommit() and not connection.in_atomic_block,
                    ReasonCode.DELIVERY_UNKNOWN)
            count(expected_count, self.limits.max_actions)
            require(expected_count > 0, ReasonCode.INVALID_VALUE)
            digest(expected_tail)
            material = self.keys.resolve(recipient, KeyPurpose.BACKUP_PUBLIC, self.service_identity)
            if isinstance(material, ProtectionError):
                return material
            public = bytes(material.borrow(KeyPurpose.BACKUP_PUBLIC)).strip()
            require(re.fullmatch(rb'age1[0-9a-z]{58}', public), ReasonCode.KEY_UNAVAILABLE)
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                    cursor.execute('SELECT txid_current_snapshot()::text')
                    consistency = cursor.fetchone()[0]
                    # Bound each database row before loading JSON into the Python process.
                    for table in ('audit_auditledgerentry', 'audit_securityauditrecord'):
                        where = ('' if table == 'audit_auditledgerentry' else
                            " WHERE ledger_entry_id IS NOT NULL OR event->>'schema_version'='ds.security-event.v1'")
                        cursor.execute('SELECT count(*), COALESCE(max(octet_length(row_to_json(t)::text)),0) '
                                       'FROM ' + table + ' t' + where)
                        rows, largest = cursor.fetchone()
                        require(rows <= self.limits.max_actions and largest <= self.limits.max_json_bytes,
                                ReasonCode.LIMIT_EXCEEDED)
                entries = AuditLedgerEntry.objects.order_by('id')
                require(entries.count() == expected_count and not entries.exclude(chain_version='v1').exists(),
                        ReasonCode.REPORT_MISMATCH)
                tail = entries.last()
                require(tail.current_hash == expected_tail, ReasonCode.REPORT_MISMATCH)
                checked = AuditLedgerService.verify_chain(entries=entries.iterator(chunk_size=1))
                require(checked.is_valid and checked.checked_count == expected_count, ReasonCode.AUDIT_UNAVAILABLE)
                records = SecurityAuditRecord.objects.filter(
                    Q(ledger_entry__isnull=False) | Q(event__schema_version='ds.security-event.v1')).order_by('id')
                record_count = records.count()
                header = dict(format='ds.legacy-audit-archive.v1', archive_ref=archive_ref,
                    approval_ref=context.authorization_ref, environment=self.environment.value, domain=self.domain,
                    consistency_point=consistency, chain_version='v1', chain_length=expected_count,
                    tail_id=tail.pk, tail_hash=expected_tail, security_records=record_count,
                    legacy_timestamps_authenticated=False, security_records_authenticated=False)
                key_fd = os.memfd_create('legacy-archive-recipient', os.MFD_CLOEXEC)
                os.write(key_fd, public + b'\n')
                os.lseek(key_fd, 0, os.SEEK_SET)
                with os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
                    process = subprocess.Popen([self.age, '--encrypt', '--recipients-file', f'/proc/self/fd/{key_fd}'],
                        stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL, pass_fds=(key_fd,))
                    process.stdin.write((json.dumps(header, sort_keys=True) + '\n').encode())
                    for kind, source in (('ledger', entries), ('security-record', records)):
                        for row in source.values().iterator(chunk_size=1):
                            line = json.dumps({'kind': kind, 'row': row}, ensure_ascii=False,
                                              separators=(',', ':'), default=str).encode('utf-8')
                            require(len(line) <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
                            process.stdin.write(line + b'\n')
                    process.stdin.close()
                    require(process.wait() == 0, ReasonCode.SOURCE_NOT_APPROVED)
                    output.flush()
                    os.fsync(output.fileno())
            with partial.open('rb') as source:
                ciphertext_hash = hashlib.file_digest(source, 'sha256').hexdigest()
            size = partial.stat().st_size
            partial.rename(final)
            stored = StoredObject(schema_version=StoredObject.SCHEMA, object_ref=archive_ref,
                version='ds.legacy-audit-archive.v1', ciphertext_hash=ciphertext_hash, size_bytes=size, state='verified')
            event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                event_id='archive/' + object_id, kind=EventKind.BACKUP, actor_ref=context.actor_ref,
                object_ref=archive_ref, object_version=stored.version, outcome=Outcome.SUCCEEDED,
                occurred_at=self.clock(), counts=(('records', expected_count), ('processed', record_count)),
                policy_binding=self.policy_binding, algorithm_versions=('legacy/v1', 'age/v1'),
                key_versions=(recipient.version,), correlation_ref=context.trace_id, reason=None,
                evidence_hashes=(('archive', ciphertext_hash), ('report', expected_tail)))
            metadata = dict(header, stored=stored.to_wire(), bridge_event=event.to_wire(), bridge_state='pending')
            with os.fdopen(os.open(self.directory / (object_id + '.legacy.json'),
                                  os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
                json.dump(metadata, output, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return stored, event
        except ContractViolation as error:
            code = error.code
        except (OSError, DatabaseError, ValueError):
            code = ReasonCode.DELIVERY_UNKNOWN
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                process.wait()
                if not process.stdin.closed:
                    with suppress(BrokenPipeError):
                        process.stdin.close()
            if key_fd is not None:
                os.close(key_fd)
        # Failed/unknown encrypted output remains isolated; never report it as a bridged archive.
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=archive_ref)
