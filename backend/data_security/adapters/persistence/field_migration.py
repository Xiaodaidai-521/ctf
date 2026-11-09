"""Backup-gated owner-field backfill with a metadata-only restart checkpoint."""
import hashlib
import json
import os
from pathlib import Path

from django.db import DatabaseError, connection, transaction

from data_security.adapters.persistence.backup import _measure
from data_security.adapters.persistence import fields
from data_security.adapters.persistence.fields import ProtectedModel
from data_security.contracts import ContractViolation, FrozenJSON, ReasonCode
from data_security.contracts.schema import canonical_bytes, require


class FieldBackfill:
    def __init__(self, *, models, storage):
        require(fields._adapter is storage and storage is not None, ReasonCode.KEY_UNAVAILABLE)
        self.models = {model._meta.label_lower: model for model in models}
        self.storage = storage
        quote = connection.ops.quote_name
        self.checks = tuple((
            'fields/' + label,
            'SELECT ' + ', '.join(quote(name) + '::text' for name in (
                'id', 'security_uuid', 'security_revision', *model.encrypted_fields, *model.redacted_fields, *model.minimized_fields)) +
            ' FROM ' + quote(model._meta.db_table) + " WHERE security_state = 'legacy-v0' ORDER BY id"
        ) for label, model in self.models.items())

    def inventory(self):
        result = {}
        for label, model in self.models.items():
            counts = {name: 0 for name in (*model.encrypted_fields, *model.redacted_fields, *model.minimized_fields)}
            rows = model.objects.filter(security_state='legacy-v0').values(*counts)
            for row in rows.iterator():
                for name, value in row.items():
                    pending = [value]
                    while pending:
                        item = pending.pop()
                        if isinstance(item, dict):
                            pending.extend(item.values())
                        elif isinstance(item, list):
                            pending.extend(item)
                        elif isinstance(item, str) and item.startswith('gAAAAA'):
                            counts[name] += 1
            result[label] = {'legacy_rows': rows.count(), 'fernet_candidates': counts}
        return result

    def prepare(self, *, checkpoint, recovery):
        require(connection.vendor == 'postgresql', ReasonCode.AUTHORIZATION_DENIED)
        path = Path(checkpoint)
        require(path.is_absolute() and not path.exists() and not path.parent.stat().st_mode & 0o077,
                ReasonCode.AUTHORIZATION_DENIED)
        # This is the durable record produced by PostgresAgeBackup.restore, not a test-run exit code.
        require(type(recovery) is dict and recovery.get('durability') == 'durable' and
                str(recovery.get('event_id', '')).startswith('backup-restore/') and
                str(recovery.get('backup_ref', '')).startswith('backup/'), ReasonCode.SOURCE_NOT_APPROVED)
        inventory = self.inventory()
        require(not any(count for item in inventory.values() for count in item['fernet_candidates'].values()),
                ReasonCode.UNSUPPORTED_FORMAT)
        entries = []
        with transaction.atomic():
            for label, model in self.models.items():
                for obj in model.objects.select_for_update().filter(security_state='legacy-v0').order_by('pk'):
                    values = {name: getattr(obj, name) for name in (*model.encrypted_fields, *model.redacted_fields, *model.minimized_fields)}
                    entries.append({'model': label, 'pk': obj.pk, 'revision': obj.security_revision,
                        'source_hash': hashlib.sha256(canonical_bytes(FrozenJSON(values), include_payload=True)).hexdigest(), 'status': 'pending', 'reason': None})
            require(recovery.get('checks') == _measure(connection.connection, self.checks),
                    ReasonCode.REPORT_MISMATCH)
            document = {'schema_version': 'ds.field-backfill.v1', 'backup_ref': recovery['backup_ref'],
                        'recovery_event': recovery['event_id'], 'entries': entries, 'accepted': False}
            self._persist(path, document)
        return self.counts(document)

    def run(self, *, checkpoint, limit=100, retry_failed=False):
        require(type(limit) is int and 1 <= limit <= 1000 and type(retry_failed) is bool,
                ReasonCode.INVALID_VALUE)
        path, document = self._load(checkpoint)
        require(not document['accepted'], ReasonCode.IDEMPOTENCY_CONFLICT)
        selected = [item for item in document['entries'] if item['status'] == 'pending' or
                    retry_failed and item['status'] == 'failed'][:limit]
        for item in selected:
            model = self.models[item['model']]
            try:
                with transaction.atomic():
                    obj = model.objects.select_for_update().get(pk=item['pk'])
                    if obj.security_state == 'sealed-v1':
                        # A concurrent business save may already have migrated this row.
                        for name in model.encrypted_fields:
                            self.storage.read(obj, name)
                    else:
                        values = {name: getattr(obj, name) for name in (*model.encrypted_fields, *model.redacted_fields, *model.minimized_fields)}
                        require(obj.security_state == 'legacy-v0' and obj.security_revision == item['revision'] and
                                hashlib.sha256(canonical_bytes(FrozenJSON(values), include_payload=True)).hexdigest() == item['source_hash'], ReasonCode.IDEMPOTENCY_CONFLICT)
                        # Backfill is storage, not a replay of Submission.save's judging/score effects.
                        ProtectedModel.save(obj, _legacy_migration=True)
                    item['status'], item['reason'] = 'succeeded', None
            except (ContractViolation, RuntimeError, DatabaseError, model.DoesNotExist):
                item['status'], item['reason'] = 'failed', 'FIELD_BACKFILL_FAILED'
            self._persist(path, document)
        return self.counts(document)

    def finish(self, *, checkpoint):
        path, document = self._load(checkpoint)
        counts = self.counts(document)
        require(counts['failed'] == counts['unprocessed'] == 0 and not self.storage.legacy_reads and
                len(self.storage.index_keys) == 1, ReasonCode.SOURCE_NOT_APPROVED)
        conflicts = []
        with transaction.atomic():
            for label, model in self.models.items():
                require(not model.objects.exclude(security_state='sealed-v1').exists(), ReasonCode.SOURCE_NOT_APPROVED)
                emails = {}
                for obj in model.objects.all().iterator():
                    require(all(getattr(obj, name) == value for name, value in model.minimized_fields.items()),
                            ReasonCode.REPORT_MISMATCH)
                    for name in model.encrypted_fields:
                        value = self.storage.read(obj, name)
                        require(getattr(obj, name) in ('', {}), ReasonCode.REPORT_MISMATCH)
                        if name == 'email':
                            require((obj.email_index, obj.email_index_previous) == self.storage.email_indexes(obj, value),
                                    ReasonCode.REPORT_MISMATCH)
                            if value:
                                if value in emails:
                                    conflicts.append({'model': label, 'rows': [emails[value], obj.pk]})
                                else:
                                    emails[value] = obj.pk
            if conflicts:
                document['conflicts'] = conflicts
                self._persist(path, document)
                return {**counts, 'accepted': False, 'conflicts': len(conflicts)}
            # The database now rejects an old/unbound writer, not just a config flag.
            with connection.cursor() as cursor:
                for model in self.models.values():
                    table = connection.ops.quote_name(model._meta.db_table)
                    constraint = connection.ops.quote_name(model._meta.db_table + '_sealed_only')
                    cursor.execute('SELECT 1 FROM pg_constraint WHERE conrelid=%s::regclass AND conname=%s',
                                   [model._meta.db_table, model._meta.db_table + '_sealed_only'])
                    if not cursor.fetchone():
                        cursor.execute(f'ALTER TABLE {table} ADD CONSTRAINT {constraint} CHECK (security_state = \'sealed-v1\')')
            document['accepted'] = True
            document.pop('conflicts', None)
        self._persist(path, document)
        return {**counts, 'accepted': True, 'conflicts': 0}

    @staticmethod
    def counts(document):
        entries = document['entries']
        return {'eligible': len(entries), 'succeeded': sum(item['status'] == 'succeeded' for item in entries),
                'failed': sum(item['status'] == 'failed' for item in entries),
                'unprocessed': sum(item['status'] == 'pending' for item in entries)}

    def _load(self, checkpoint):
        path = Path(checkpoint)
        require(path.is_absolute() and not path.stat().st_mode & 0o077, ReasonCode.AUTHORIZATION_DENIED)
        document = json.loads(path.read_bytes())
        require(type(document) is dict and document.get('schema_version') == 'ds.field-backfill.v1' and
                type(document.get('entries')) is list and type(document.get('accepted')) is bool,
                ReasonCode.INVALID_VALUE)
        for item in document['entries']:
            require(type(item) is dict and set(item) == {'model', 'pk', 'revision', 'source_hash', 'status', 'reason'} and
                    item['model'] in self.models and type(item['pk']) is int and type(item['revision']) is int and
                    type(item['source_hash']) is str and item['status'] in ('pending', 'succeeded', 'failed'),
                    ReasonCode.INVALID_VALUE)
        return path, document

    @staticmethod
    def _persist(path, document):
        temporary = path.with_suffix('.partial')
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as stream:
            json.dump(document, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
