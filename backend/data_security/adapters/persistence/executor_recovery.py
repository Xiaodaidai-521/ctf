"""Isolated executor inspection. Retained preparations and old receipts are never promoted."""
from dataclasses import replace
import hashlib

from django.db import DatabaseError, connection, transaction
from controlled_export.errors import ControlledExportError
from controlled_export.models import DeliveryAttempt, ExecutionAttempt, ExportExecution, OutboxEvent, ProtectedArtifact, ShareGrant

from data_security.contracts import ContractViolation, Environment, ObjectContext, ProtectionError, ReasonCode, StoredObject
from data_security.contracts.schema import require
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject


class DjangoExecutorRecoveryVerifier:
    def __init__(self, *, store, inspect_attempt, backup, project_ref, limits, clock):
        self.store, self.inspect_attempt, self.backup = store, inspect_attempt, backup
        self.project_ref, self.limits, self.clock = project_ref, limits, clock

    def _rows(self, query):
        require(query.count() <= self.limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
        return query.iterator(chunk_size=1)

    def __call__(self, context):
        try:
            require(connection.vendor == 'postgresql' and connection.get_autocommit()
                    and not connection.in_atomic_block and self.backup._allowed(context)
                    and context.environment is Environment.EVALUATION, ReasonCode.SOURCE_NOT_APPROVED)
            configured, target = connection.settings_dict, self.backup.database
            require((configured['NAME'], configured['HOST'], str(configured['PORT'] or 5432)) ==
                    (target['dbname'], target['host'], str(target.get('port', 5432))), ReasonCode.SOURCE_NOT_APPROVED)
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                return self._inspect()
        except ContractViolation as error:
            code = error.code
        except (ControlledExportError, DatabaseError, OSError, KeyError, TypeError, ValueError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=context.trace_id)

    def _inspect(self):
        objects = {row.object_ref: row for row in self._rows(PrivateObject.objects.all())}
        inspected, key_refs, pending = {}, set(), 0
        for operation in self._rows(PrivateFileOperation.objects.all()):
            require(operation.actor_ref == 'service/controlled-export'
                    and operation.scope_ref == 'controlled-export/preparations' and not operation.legacy_sources
                    and operation.operation_ref == 'executor-preparation/' + str(operation.object_uuid)
                    and operation.state in ('preparing', 'prepared'), ReasonCode.SOURCE_NOT_APPROVED)
            require(operation.field_refs == ['controlled-export/output']
                    and set(operation.files) <= set(operation.field_refs), ReasonCode.REPORT_MISMATCH)
            if not operation.files:
                pending += 1
                continue
            item = operation.files['controlled-export/output']
            context, stored = ObjectContext(**{**item['context'], 'environment': Environment(item['context']['environment'])}), StoredObject.from_wire(item['stored'])
            require(context.project_ref == self.project_ref and context.field_ref == 'controlled-export/output'
                    and context.object_uuid == str(operation.object_uuid) and context.object_version == '1',
                    ReasonCode.REPORT_MISMATCH)
            if stored.object_ref not in objects:
                require(operation.state == 'preparing', ReasonCode.CIPHERTEXT_INVALID)
                pending += 1
                continue
            envelope = self.store.inspect_recovery(stored, context)
            if isinstance(envelope, ProtectionError):
                raise ContractViolation(envelope.code)
            require(envelope is not None, ReasonCode.CIPHERTEXT_INVALID)
            payload = self.store.crypto.open(envelope, context, envelope.key)
            if isinstance(payload, ProtectionError):
                raise ContractViolation(payload.code)
            actual_hash = hashlib.sha256(payload.binary).hexdigest()
            require(actual_hash == item['input_hash'] == operation.request_hash, ReasonCode.HASH_MISMATCH)
            inspected[stored.object_ref] = context, stored, actual_hash
            key_refs.add(envelope.key.key_ref)
        for object_ref, row in objects.items():
            require(row.state in ('candidate', 'verified', 'retired'), ReasonCode.SOURCE_NOT_APPROVED)
            if object_ref not in inspected:
                pending += 1

        states, expired, legacy_files = {}, 0, 0
        for execution in self._rows(ExportExecution.objects.all()):
            require(execution.state in dict(ExportExecution.STATE), ReasonCode.REPORT_MISMATCH)
            states[execution.state] = states.get(execution.state, 0) + 1
            expired += int(execution.valid_until <= self.clock())
        attempts = {}
        for attempt in self._rows(ExecutionAttempt.objects.select_related('execution')):
            require(attempt.status in dict(ExecutionAttempt.STATUS), ReasonCode.REPORT_MISMATCH)
            attempts[attempt.status] = attempts.get(attempt.status, 0) + 1
            legacy_files += int(bool(attempt.candidate_storage_ref))
            if not attempt.private_candidate:
                continue
            context = self.inspect_attempt(execution=attempt.execution, attempt=attempt, private_project_ref=self.project_ref)
            document = attempt.private_candidate
            if 'stored' not in document:
                pending += 1
                continue
            stored = StoredObject.from_wire(document['stored'])
            require(stored.object_ref in inspected, ReasonCode.CIPHERTEXT_INVALID)
            actual_context, actual_stored, actual_hash = inspected[stored.object_ref]
            require(context == actual_context and stored == replace(actual_stored, state='verified')
                    and document['output_content_hash'] == actual_hash
                    and document['scope_hash'] == attempt.execution.scope_hash
                    and document['plan_hash'] == attempt.execution.plan_hash, ReasonCode.REPORT_MISMATCH)

        for artifact in self._rows(ProtectedArtifact.objects.all()):
            legacy_files += int(bool(artifact.private_storage_ref))
        shares = {'retained': 0, 'expired': 0, 'revoked': 0}
        for share in self._rows(ShareGrant.objects.all()):
            shares['retained'] += 1
            shares['expired'] += int(share.expires_at <= self.clock())
            shares['revoked'] += int(share.revoked_at is not None)
        deliveries = {}
        for delivery in self._rows(DeliveryAttempt.objects.all()):
            require(delivery.status in dict(DeliveryAttempt.STATUS), ReasonCode.REPORT_MISMATCH)
            deliveries[delivery.status] = deliveries.get(delivery.status, 0) + 1
        outbox = sum(1 for _ in self._rows(OutboxEvent.objects.all()))
        return {'complete': True, 'opening_allowed': legacy_files == 0, 'governance': {},
            'scope': 'executor-preparation-only', 'private_objects_opened': len(inspected),
            'data_key_refs': sorted(key_refs), 'key_retirement_allowed': False, 'pending_records': pending,
            'legacy_files_not_in_private_bundle': legacy_files, 'executions': states,
            'expired_executions': expired, 'attempts': attempts, 'shares': shares, 'delivery_records': deliveries,
            'historical_outbox_records': outbox, 'outbox_authenticated_as_v2': False}
