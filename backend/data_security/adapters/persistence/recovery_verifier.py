"""Read-only restored backend inspection, not publication or renewed authorization."""
from dataclasses import replace
from datetime import datetime
import hashlib
import json

from django.db import DatabaseError, connection, transaction
from django.db.models import Q

from audit.models import AuditLedgerEntry, AuditLedgerLock, SecurityAuditRecord
from audit.services import AuditLedgerService
from export_quota.models import QuotaBucket, QuotaReservation
from feedback_center.models import FeedbackAttachment
from resources.models import Resource
from data_security.contracts import (
    AuditReceipt, DeliveryReceipt, Environment, EventKind, ObjectContext, Outcome, ProtectionError, ReasonCode, Role, Purpose,
    StoredObject, ContractViolation, content_hash,
)
from data_security.contracts.schema import require
from data_security.adapters.persistence.models import ExportReport, PrivateFileOperation, PrivateFileShare, PrivateObject
from data_security.adapters.persistence.private_maintenance import DjangoPrivateMaintenance


def _result(value):
    if isinstance(value, ProtectionError):
        raise ContractViolation(value.code)
    return value


class DjangoRecoveryVerifier:
    def __init__(self, *, store, owners, audit, reports, verify_report, field_storage, field_models,
                 inspect_share, limits, clock, database, archives=None, archive_identity=None, export_lifecycle=None):
        self.store, self.owners, self.audit, self.reports = store, owners, audit, reports
        self.verify_report, self.field_storage, self.field_models = verify_report, field_storage, field_models
        self.inspect_share, self.limits, self.clock, self.database = inspect_share, limits, clock, database
        self.archives, self.archive_identity = archives, archive_identity
        self.export_lifecycle = export_lifecycle

    def _rows(self, query):
        require(query.count() <= self.limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
        return query.iterator(chunk_size=1)

    def __call__(self, context):
        try:
            require(connection.vendor == 'postgresql' and connection.get_autocommit()
                    and not connection.in_atomic_block and context.environment is self.store.environment
                    and context.environment in (Environment.TEST, Environment.EVALUATION)
                    and context.actor_ref == 'service/security' and context.domain == 'ctf'
                    and context.role is Role.SERVICE and context.purpose is Purpose.STORAGE,
                    ReasonCode.SOURCE_NOT_APPROVED)
            configured = connection.settings_dict
            require((configured['NAME'], configured['HOST'], str(configured['PORT'] or 5432)) ==
                    (self.database['dbname'], self.database['host'], str(self.database.get('port', 5432))),
                    ReasonCode.SOURCE_NOT_APPROVED)
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                return self._inspect(context)
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError, KeyError, ValueError, TypeError, RuntimeError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
            retryable=False, trace_id=context.trace_id)

    def _inspect(self, context):
        audit = _result(self.audit.inspect_recovery(self.limits))

        def read_event(event_id):
            require(event_id in audit['events'], ReasonCode.AUDIT_UNAVAILABLE)
            return audit['events'][event_id][0]

        objects = {row.object_ref: row for row in self._rows(PrivateObject.objects.all())}
        opened, data_keys, governance, operations = {}, set(), {}, {}
        pending, legacy_files, legacy_fields, retired, terminal_operations = 0, 0, 0, 0, 0

        def open_object(stored, object_context):
            # Also check every reference to a shared object; caching never bypasses its identity.
            envelope = _result(self.store.inspect_recovery(stored, object_context))
            if envelope is None:
                return None
            payload = _result(self.store.crypto.open(envelope, object_context, envelope.key))
            data_keys.add(envelope.key.key_ref)
            opened[stored.object_ref] = envelope.key.key_ref
            return payload

        for row in self._rows(PrivateFileOperation.objects.all()):
            operations[row.operation_ref] = row
            require(row.state in ('preparing', 'prepared', 'committed', 'aborted', 'retired', 'cleaned')
                    and type(row.files) is dict and type(row.field_refs) is list
                    and set(row.files) <= set(row.field_refs), ReasonCode.REPORT_MISMATCH)
            complete = bool(row.files) and set(row.files) == set(row.field_refs)
            for field, item in row.files.items():
                object_context, stored = ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])}), StoredObject.from_wire(item['stored'])
                owner = {'resources/file': 'resources', 'resources/cover_image': 'resources',
                         'feedback/attachment': 'feedback'}.get(field)
                require(owner is not None and object_context.object_uuid == str(row.object_uuid)
                        and object_context.field_ref == field
                        and object_context.project_ref == self.owners[owner].project_ref, ReasonCode.REPORT_MISMATCH)
                if stored.object_ref not in objects:
                    require(row.state in ('preparing', 'aborted', 'retired', 'cleaned'), ReasonCode.CIPHERTEXT_INVALID)
                    complete = False
                    continue  # Retained intention, not permission to reconstruct registration.
                payload = open_object(stored, object_context)
                if payload is None:
                    require(row.state in ('aborted', 'retired', 'cleaned'), ReasonCode.CIPHERTEXT_INVALID)
                    complete = False
                    continue
                require(hashlib.sha256(payload.binary).hexdigest() == item['input_hash'], ReasonCode.HASH_MISMATCH)
                if row.legacy_sources:
                    source = row.legacy_sources['sources'][field]
                    require(source['sha256'] == item['input_hash'] and source['size_bytes'] == len(payload.binary)
                            and opened[stored.object_ref] == row.legacy_sources['data_key_ref'], ReasonCode.HASH_MISMATCH)
            if row.state in ('preparing', 'prepared'):
                pending += 1
            elif row.state in ('aborted', 'retired', 'cleaned'):
                terminal_operations += 1
            if row.legacy_sources and complete and row.state in ('prepared', 'committed', 'retired'):
                require(row.legacy_sources['schema_version'] == 'ds.legacy-files.v1'
                        and set(row.legacy_sources['sources']) == set(row.field_refs), ReasonCode.REPORT_MISMATCH)
                governance[row.operation_ref] = DjangoPrivateMaintenance.source_hash(row)

        for row in self._rows(Resource.objects.all()):
            if not row.private_files:
                legacy_files += int(bool(row.file)) + int(bool(row.cover_image))
                continue
            for _, object_context, stored in _result(self.owners['resources'].inspect_recovery(row, read_event=read_event)):
                if open_object(stored, object_context) is None:
                    operation = operations.get(row.private_files.get('operation_ref'))
                    require(operation is not None and operation.state in ('retired', 'cleaned')
                            and operation.result_ref == str(row.pk), ReasonCode.CIPHERTEXT_INVALID)
                    item = operation.files[object_context.field_ref]
                    require(item['context'] == object_context.to_wire() and stored == replace(
                        StoredObject.from_wire(item['stored']), state='verified'), ReasonCode.REPORT_MISMATCH)
        for row in self._rows(FeedbackAttachment.objects.select_related('ticket')):
            if not row.private_file:
                legacy_files += int(bool(row.file))
                continue
            object_context, stored = _result(self.owners['feedback'].inspect_recovery(row, read_event=read_event))
            payload = open_object(stored, object_context)
            if payload is None:
                operation = operations.get(row.private_file.get('operation_ref'))
                require(operation is not None and operation.state in ('retired', 'cleaned')
                        and operation.result_ref == str(row.attachment_id), ReasonCode.CIPHERTEXT_INVALID)
                item = operation.files[object_context.field_ref]
                require(item['context'] == object_context.to_wire() and stored == replace(
                    StoredObject.from_wire(item['stored']), state='verified'), ReasonCode.REPORT_MISMATCH)
            else:
                require(len(payload.binary) == row.size and hashlib.sha256(payload.binary).hexdigest() == row.sha256,
                        ReasonCode.HASH_MISMATCH)

        report_count, logical_deliveries, report_keys = 0, 0, set()
        retention_facts, retained_executions = {}, set()
        if self.export_lifecycle is not None and self.export_lifecycle.journal is not None:
            retention_facts = {fact['export']['execution_id']: fact
                               for fact in self.export_lifecycle.journal.read()['facts']}
            for fact in retention_facts.values():
                receipt = AuditReceipt.from_wire(fact['intent'])
                require(receipt.event_id in audit['events'] and audit['events'][receipt.event_id][1] == receipt,
                        ReasonCode.AUDIT_UNAVAILABLE)
        enrolled = {event.object_ref: event.correlation_ref for event, _ in audit['events'].values()
                    if event.algorithm_versions == ('ds.export-lifecycle.v1', 'register')}
        for row in self._rows(ExportReport.objects.all()):
            if row.retention_scope is not None or row.execution_id in enrolled:
                require(self.export_lifecycle is not None and self.export_lifecycle.journal is not None
                        and row.retention_scope == self.export_lifecycle.scope_ref == enrolled.get(row.execution_id),
                        ReasonCode.SOURCE_NOT_APPROVED)
            if row.execution_id in retention_facts:
                require(row.state == 'retired', ReasonCode.SOURCE_NOT_APPROVED)
                retained_executions.add(row.execution_id)
            binding = _result(self.reports.load_binding(row.execution_id))
            record = _result(self.reports.read(binding))
            if record is None:
                require(row.delivery_receipt is None and row.state != 'retiring', ReasonCode.REPORT_MISMATCH)
                if row.state == 'retired':
                    require(self.export_lifecycle is not None, ReasonCode.REPORT_MISMATCH)
                    self.export_lifecycle.verify_retired(row, None, binding, audit['events'], retention_facts)
                else:
                    pending += 1
                continue
            require(_result(self.verify_report(record)) is True, ReasonCode.REPORT_MISMATCH)
            report_keys.add(record.proof.key.key_ref)
            require(row.state != 'retiring', ReasonCode.SOURCE_NOT_APPROVED)
            payload = open_object(record.stored, record.context)
            if row.state == 'retired':
                require(payload is None and self.export_lifecycle is not None, ReasonCode.REPORT_MISMATCH)
                self.export_lifecycle.verify_retired(row, record, binding, audit['events'], retention_facts)
            elif payload is None:
                require(row.state == 'aborted' and row.delivery_receipt is None, ReasonCode.REPORT_MISMATCH)
            else:
                require(hashlib.sha256(payload.binary).hexdigest() == record.report.output_hash, ReasonCode.HASH_MISMATCH)
            report_count += 1
            if row.state in ('prepared', 'retired'):
                receipt = (_result(self.reports.delivery(binding)) if row.state == 'prepared' else
                           DeliveryReceipt.from_wire(row.delivery_receipt) if row.delivery_receipt is not None else None)
                if receipt is not None:
                    event = read_event(receipt.audit.event_id)
                    require(audit['events'][receipt.audit.event_id][1] == receipt.audit and
                        (event.event_id, event.kind, event.actor_ref, event.object_ref, event.object_version,
                         event.outcome, event.counts, event.policy_binding, event.algorithm_versions,
                         event.key_versions, event.correlation_ref, event.reason, event.evidence_hashes) ==
                        (content_hash({'domain': 'ds.logical-delivery.v1', 'binding': binding}), EventKind.DELIVERY,
                         binding.subject_ref, record.stored.object_ref, record.stored.version, Outcome.SUCCEEDED,
                         (('records', receipt.delivered_records),), binding.policy_binding, record.report.algorithm_versions,
                         (record.proof.key.key_ref,), binding.execution_id, None,
                         (('ciphertext', record.stored.ciphertext_hash), ('report', content_hash(record.report)))),
                        ReasonCode.AUDIT_UNAVAILABLE)
                    logical_deliveries += 1  # Original logical receipt, never network completion.
                elif row.state == 'prepared':
                    pending += 1

        for execution_id in retention_facts.keys() - retained_executions:
            item = retention_facts[execution_id]['export']
            path = self.export_lifecycle.store.root / (item['object_ref'].removeprefix('private/') + '.sealed')
            require(item['object_ref'] not in objects and not path.exists() and not path.is_symlink(),
                    ReasonCode.SOURCE_NOT_APPROVED)

        for object_ref, row in objects.items():
            require(row.state in ('candidate', 'verified', 'published', 'retired'), ReasonCode.REPORT_MISMATCH)
            if row.state == 'retired':
                retired += 1
            elif object_ref not in opened:
                require(row.state != 'published', ReasonCode.SOURCE_NOT_APPROVED)
                pending += 1  # Opaque unmatched candidates stay inaccessible and unchanged.

        fields, index_keys = 0, set()
        for model in self.field_models:
            for row in self._rows(model._base_manager.all()):
                if row.security_state == 'legacy-v0':
                    legacy_fields += int(any(getattr(row, name) not in ('', None, {}, [])
                        for name in (*row.encrypted_fields, *row.redacted_fields)))
                    continue
                require(row.security_state == 'sealed-v1', ReasonCode.CIPHERTEXT_INVALID)
                require(self.field_storage is not None, ReasonCode.KEY_UNAVAILABLE)
                require(all(getattr(row, name) == value for name, value in row.minimized_fields.items()),
                        ReasonCode.REPORT_MISMATCH)
                for name in row.encrypted_fields:
                    value = self.field_storage.read(row, name)
                    require(getattr(row, name) in ('', {}), ReasonCode.REPORT_MISMATCH)
                    if name == 'email':
                        require((row.email_index, row.email_index_previous) == self.field_storage.email_indexes(row, value),
                                ReasonCode.REPORT_MISMATCH)
                        if value:
                            index_keys.update(key.key_ref for key in self.field_storage.index_keys)
                    data_keys.add(row.security_envelopes[name]['envelope']['key']['key_ref'])
                    fields += 1

        quota_states = {state: 0 for state, _ in QuotaReservation.STATE}
        quota_states['expired_reserved'] = 0
        for row in self._rows(QuotaBucket.objects.all()):
            require(min(row.limit, row.settled, row.active_reserved, row.unknown_reserved) >= 0,
                    ReasonCode.REPORT_MISMATCH)
        for row in self._rows(QuotaReservation.objects.all()):
            require(row.state in dict(QuotaReservation.STATE) and 0 <= row.settled_amount <= row.amount,
                    ReasonCode.REPORT_MISMATCH)
            quota_states[row.state] += 1
            if row.state == 'reserved' and row.expires_at is not None and row.expires_at <= self.clock():
                quota_states['expired_reserved'] += 1

        shares = {'retained': 0, 'expired': 0, 'revoked': 0}
        for row in self._rows(PrivateFileShare.objects.all()):
            inspected = _result(self.inspect_share(row.share_id, read_event))
            require(inspected.document == row.document, ReasonCode.REPORT_MISMATCH)
            shares['retained'] += 1
            shares['expired'] += int(datetime.fromisoformat(row.document['expires_at']) <= self.clock())
            shares['revoked'] += int(row.revoked_at is not None)

        legacy = self._legacy_audit(context, audit, governance)
        return {'complete': True, 'opening_allowed': not (legacy_files or legacy_fields),
            'governance': governance, 'private_objects_opened': len(opened), 'retired_objects': retired,
            'pending_records': pending, 'terminal_operations': terminal_operations,
            'legacy_files_not_in_private_bundle': legacy_files,
            'legacy_field_rows': legacy_fields, 'encrypted_fields_opened': fields,
            'reports_authenticated': report_count, 'logical_delivery_receipts': logical_deliveries,
            'quota': quota_states, 'shares': shares, 'data_key_refs': sorted(data_keys),
            'audit_key_refs': audit['key_refs'], 'report_key_refs': sorted(report_keys), 'index_key_refs': sorted(index_keys),
            'archive_identity_refs': [self.archive_identity.key_ref] if 'archive_ref' in legacy else [],
            'key_retirement_allowed': False, 'key_inventory_scope': 'verified-restored-owners',
            'external_key_inventory_required': ['retained-backups', 'other-archives', 'other-checkpoints'],
            'legacy_audit': legacy,
            'audit_tail': audit['tail'].to_wire(), 'audit_checkpoint': self.audit.checkpoint_ref,
            'audit_unanchored_suffix': audit['tail'].sequence - audit['checkpoint'].receipt.sequence}

    def _legacy_audit(self, context, audit, governance):
        entries = AuditLedgerEntry._base_manager.order_by('id')
        records = SecurityAuditRecord._base_manager.filter(
            Q(ledger_entry__isnull=False) | Q(event__schema_version='ds.security-event.v1')).order_by('id')
        digest = hashlib.sha256()
        for kind, query in (('ledger', entries), ('security-record', records)):
            for row in self._rows(query.values()):
                encoded = json.dumps({'kind': kind, 'row': row}, ensure_ascii=False, sort_keys=True,
                    separators=(',', ':'), default=str).encode('utf-8') + b'\n'
                require(len(encoded) <= self.limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
                digest.update(encoded)
        metadata = AuditLedgerLock.objects.filter(key='default').values_list('legacy_archive', flat=True).first()
        if not metadata:
            require(AuditLedgerService.verify_chain(entries=entries).is_valid, ReasonCode.AUDIT_UNAVAILABLE)
            if entries.exists():
                governance['audit/legacy-v1'] = digest.hexdigest()
            return {'state': 'historical-v1', 'records': entries.count(), 'security_records': records.count(),
                'content_hash': digest.hexdigest(), 'timestamps_authenticated': False}
        require(self.archives is not None and self.archive_identity is not None, ReasonCode.KEY_UNAVAILABLE)
        retained, decoded = _result(self.archives.read_governance(context, recovery=True))
        require(retained == metadata, ReasonCode.REPORT_MISMATCH)
        stored, bridge, _ = _result(self.archives.load(metadata['stored']['object_ref'], context, recovery=True))
        require(audit['events'].get(bridge.event_id, (None,))[0] == bridge, ReasonCode.AUDIT_UNAVAILABLE)
        _, source = _result(self.archives.verify_content(stored, bridge, self.archive_identity, context, with_source=True))
        require(source == metadata['source'], ReasonCode.REPORT_MISMATCH)
        for event_id, receipt in decoded.values():
            require(audit['events'].get(event_id.event_id) == (event_id, receipt), ReasonCode.AUDIT_UNAVAILABLE)
        deleted = metadata['state'] == 'deleted'
        require(entries.count() == (0 if deleted else source['records'])
                and records.count() == (0 if deleted else source['security_records'])
                and digest.hexdigest() == (hashlib.sha256().hexdigest() if deleted else source['content_hash']),
                ReasonCode.REPORT_MISMATCH)
        governance['audit/legacy-v1'] = source['content_hash']
        return {'state': metadata['state'], 'archive_ref': stored.object_ref,
            'content_hash': source['content_hash'], 'timestamps_authenticated': False}
