"""New export enrollment, approved retention and replay through the original recovery gate."""
from datetime import datetime, timedelta
import hashlib
import json
import os

from django.db import DatabaseError, connection, transaction

from audit.models import AuthenticatedAuditEntry
from data_security.contracts import (
    AuditReceipt, ContractViolation, DeliveryReceipt, Durability, Environment, EventKind, FrozenJSON, Outcome,
    ObjectContext, ProtectionError, Purpose, ReasonCode, Role, SecurityEventV2, StoredObject, canonical_bytes, content_hash,
)
from data_security.contracts.schema import require, utc
from .models import ExportReport, PrivateObject


def _result(value):
    if isinstance(value, ProtectionError):
        raise ContractViolation(value.code)
    return value


class DjangoExportLifecycle:
    def __init__(self, *, scope_ref, reports, verify_report, audit, read_event, clock, limits,
                 store=None, journal=None):
        self.scope_ref, self.reports, self.verify_report = scope_ref, reports, verify_report
        self.audit, self.read_event, self.clock, self.limits = audit, read_event, clock, limits
        self.store, self.journal = store, journal

    def _allowed(self, context, *, write=False):
        require((context.actor_ref, context.role, context.environment, context.domain, context.purpose) ==
                ('service/security', Role.SERVICE, Environment.EVALUATION, 'ctf', Purpose.STORAGE),
                ReasonCode.AUTHORIZATION_DENIED)
        if write:
            require(self.journal is not None and self.store is not None and connection.vendor == 'postgresql'
                    and connection.get_autocommit() and not connection.in_atomic_block,
                    ReasonCode.SOURCE_NOT_APPROVED)
        now = self.clock()
        utc(now)
        return now

    def _registration_event(self, binding, at):
        identity = {'domain': 'ds.export-lifecycle.v1', 'scope': self.scope_ref, 'binding': binding}
        return SecurityEventV2(schema_version=SecurityEventV2.SCHEMA, event_id=content_hash(identity),
            kind=EventKind.AUTHORIZATION, actor_ref='service/security', object_ref=binding.execution_id,
            object_version=binding.asset_version, outcome=Outcome.SUCCEEDED, occurred_at=at,
            counts=(('processed', 1),), policy_binding=binding.policy_binding,
            algorithm_versions=('ds.export-lifecycle.v1', 'register'), key_versions=(),
            correlation_ref=self.scope_ref, reason=None, evidence_hashes=(('report', content_hash(identity)),))

    def register(self, binding):
        """Called only for a newly created owner fence, in its original transaction."""
        require(connection.in_atomic_block and binding.environment == 'evaluation',
                ReasonCode.AUTHORIZATION_DENIED)
        event = self._registration_event(binding, self.clock())
        receipt = _result(self.audit.record(event, Durability.LEDGER_CONFIRMED))
        require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                ReasonCode.AUDIT_UNAVAILABLE)
        return receipt

    def _registration(self, row, binding, read_event):
        require(row.retention_scope == self.scope_ref, ReasonCode.SOURCE_NOT_APPROVED)
        receipt = AuditReceipt.from_wire(row.retention_registration)
        require(receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                ReasonCode.AUDIT_UNAVAILABLE)
        event = _result(read_event(receipt.event_id))
        require(type(event) is SecurityEventV2 and event == self._registration_event(binding, event.occurred_at),
                ReasonCode.AUDIT_UNAVAILABLE)
        return event

    def _candidate_event(self, binding, context, stored, intent_hash, at, key_ref):
        digest = content_hash({'domain': 'ds.export-candidate.v1', 'scope': self.scope_ref,
            'binding': binding, 'intent_hash': intent_hash, 'context': context,
            'stored': stored, 'generated_at': at})
        return SecurityEventV2(schema_version=SecurityEventV2.SCHEMA, event_id=digest,
            kind=EventKind.AUTHORIZATION, actor_ref='service/security', object_ref=stored.object_ref,
            object_version=stored.version, outcome=Outcome.SUCCEEDED, occurred_at=at,
            counts=(('processed', 1), ('bytes', stored.size_bytes)), policy_binding=binding.policy_binding,
            algorithm_versions=('ds.export-candidate.v1', 'stage'), key_versions=(key_ref,),
            correlation_ref=self.scope_ref, reason=None,
            evidence_hashes=(('ciphertext', stored.ciphertext_hash), ('report', digest)))

    def stage_candidate(self, plan, binding, context, envelope):
        """Commit the exact new ciphertext intention before the original store opens its file."""
        require(connection.vendor == 'postgresql' and connection.get_autocommit()
                and not connection.in_atomic_block, ReasonCode.SOURCE_NOT_APPROVED)
        require(context.environment is Environment.EVALUATION and context.field_ref == 'resources/export'
                and binding.environment == 'evaluation', ReasonCode.SOURCE_NOT_APPROVED)
        encoded = canonical_bytes(envelope)
        ciphertext_hash = hashlib.sha256(encoded).hexdigest()
        identity = content_hash(dict(project=context.project_ref, environment=context.environment,
            object_uuid=context.object_uuid, version=context.object_version, field=context.field_ref))
        stored = StoredObject(schema_version=StoredObject.SCHEMA,
            object_ref='private/' + content_hash({'context': identity, 'ciphertext': ciphertext_hash}),
            version=context.object_version, ciphertext_hash=ciphertext_hash, size_bytes=len(encoded), state='candidate')
        with transaction.atomic():
            row = ExportReport.objects.select_for_update().get(execution_id=binding.execution_id)
            require(row.binding_hash == content_hash(binding) and row.idempotency_key == binding.idempotency_key
                    and row.intent_hash == content_hash({'binding': binding, 'plan': plan, 'context': context}),
                    ReasonCode.IDEMPOTENCY_CONFLICT)
            require(row.state == 'preparing' and row.document is None and row.private_object_id is None,
                    ReasonCode.AUTHORIZATION_DENIED)
            require(row.retention_candidate is None, ReasonCode.IDEMPOTENCY_CONFLICT)
            registration = self._registration(row, binding, self.read_event)
            at = self.clock()
            require(registration.occurred_at <= at < min(plan.expires_at, binding.expires_at),
                    ReasonCode.AUTHORIZATION_EXPIRED)
            event = self._candidate_event(binding, context, stored, row.intent_hash, at, envelope.key.key_ref)
            receipt = _result(self.audit.record(event, Durability.LEDGER_CONFIRMED))
            require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id
                    and receipt.durability is Durability.LEDGER_CONFIRMED
                    and receipt.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
            row.retention_candidate = {'schema_version': 'ds.export-candidate.v1', 'intent_hash': row.intent_hash,
                'context': context.to_wire(), 'stored': stored.to_wire(), 'generated_at': at.isoformat(),
                'registration': receipt.to_wire()}
            row.save(update_fields=['retention_candidate'])
        return stored

    def _record(self, row, read_event, now):
        binding = _result(self.reports.load_binding(row.execution_id))
        event = self._registration(row, binding, read_event)
        record = _result(self.reports.read(binding))
        if record is not None:
            require(_result(self.verify_report(record)) is True and event.occurred_at <= record.report.created_at <= now,
                    ReasonCode.REPORT_MISMATCH)
        return record, event, binding

    def _candidate(self, row, binding, registration, candidate, read_event, now):
        require(type(candidate) is dict and set(candidate) == {
            'schema_version', 'intent_hash', 'context', 'stored', 'generated_at', 'registration'},
            ReasonCode.UNKNOWN_FIELD)
        require(candidate['schema_version'] == 'ds.export-candidate.v1'
                and candidate['intent_hash'] == row.intent_hash, ReasonCode.REPORT_MISMATCH)
        context = ObjectContext(**{**candidate['context'], 'environment': Environment(candidate['context']['environment'])})
        stored = StoredObject.from_wire(candidate['stored'])
        at = datetime.fromisoformat(candidate['generated_at'])
        utc(at)
        require(context.to_wire() == candidate['context'] and stored.to_wire() == candidate['stored']
                and stored.state == 'candidate' and context.environment is Environment.EVALUATION
                and context.field_ref == 'resources/export' and registration.occurred_at <= at <= now
                and at < binding.expires_at, ReasonCode.REPORT_MISMATCH)
        identity = content_hash(dict(project=context.project_ref, environment=context.environment,
            object_uuid=context.object_uuid, version=context.object_version, field=context.field_ref))
        require(stored.object_ref == 'private/' + content_hash({'context': identity, 'ciphertext': stored.ciphertext_hash})
                and stored.version == context.object_version, ReasonCode.HASH_MISMATCH)
        receipt = AuditReceipt.from_wire(candidate['registration'])
        require(receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                ReasonCode.AUDIT_UNAVAILABLE)
        event = _result(read_event(receipt.event_id))
        require(type(event) is SecurityEventV2 and len(event.key_versions) == 1 and event == self._candidate_event(
            binding, context, stored, row.intent_hash, at, event.key_versions[0]), ReasonCode.AUDIT_UNAVAILABLE)
        return context, stored, event

    def _export(self, row, stored, created_at, registration, *, owner_state=None, delivery=None):
        return {'execution_id': row.execution_id, 'binding_hash': row.binding_hash,
            'report_hash': row.document_hash or None, 'object_ref': stored.object_ref,
            'object_version': stored.version, 'ciphertext_hash': stored.ciphertext_hash,
            'size_bytes': stored.size_bytes, 'created_at': created_at.isoformat(),
            'expires_at': (created_at + timedelta(hours=24)).isoformat(),
            'owner_state': owner_state or row.state, 'registration_event_ref': registration.event_id,
            'delivery_hash': hashlib.sha256(json.dumps(delivery, sort_keys=True, separators=(',', ':'),
                ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()}

    def _intent_event(self, item, binding, at):
        domain = 'ds.export-candidate-retention.v1' if item['report_hash'] is None else 'ds.export-retention.v1'
        identity = {'domain': domain, 'scope': self.scope_ref, 'export': item}
        return SecurityEventV2(schema_version=SecurityEventV2.SCHEMA, event_id=content_hash(identity),
            kind=EventKind.AUTHORIZATION, actor_ref='service/security', object_ref=item['object_ref'],
            object_version=item['object_version'], outcome=Outcome.SUCCEEDED, occurred_at=at,
            counts=(('processed', 1), ('bytes', item['size_bytes'])), policy_binding=binding.policy_binding,
            algorithm_versions=(domain, 'retire'), key_versions=(),
            correlation_ref=self.scope_ref, reason=None,
            evidence_hashes=(('ciphertext', item['ciphertext_hash']), ('report', content_hash(identity))))

    def _delivery(self, wire, record, read_event):
        if wire is None:
            return
        receipt = DeliveryReceipt.from_wire(wire)
        require(receipt.to_wire() == wire and receipt.binding == record.binding
                and receipt.outcome is Outcome.SUCCEEDED and receipt.audit.durability is Durability.LEDGER_CONFIRMED
                and receipt.audit.chain_version == 'ds.audit.v2', ReasonCode.REPORT_MISMATCH)
        event = _result(read_event(receipt.audit.event_id))
        require(type(event) is SecurityEventV2 and
            (event.event_id, event.kind, event.actor_ref, event.object_ref, event.object_version,
             event.outcome, event.counts, event.policy_binding, event.algorithm_versions,
             event.key_versions, event.correlation_ref, event.reason, event.evidence_hashes) ==
            (content_hash({'domain': 'ds.logical-delivery.v1', 'binding': record.binding}), EventKind.DELIVERY,
             record.binding.subject_ref, record.stored.object_ref, record.stored.version, Outcome.SUCCEEDED,
             (('records', receipt.delivered_records),), record.binding.policy_binding, record.report.algorithm_versions,
             (record.proof.key.key_ref,), record.binding.execution_id, None,
             (('ciphertext', record.stored.ciphertext_hash), ('report', content_hash(record.report)))),
            ReasonCode.AUDIT_UNAVAILABLE)

    def _fact(self, fact, row, record, registration, read_event):
        require(type(fact) is dict and set(fact) == {'export', 'delivery', 'intent'}, ReasonCode.UNKNOWN_FIELD)
        item = fact['export']
        require(item['owner_state'] in ('prepared', 'aborted') and item == self._export(
            row, record.stored, record.report.created_at, registration,
            owner_state=item['owner_state'], delivery=fact['delivery']),
            ReasonCode.REPORT_MISMATCH)
        receipt = AuditReceipt.from_wire(fact['intent'])
        require(receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                ReasonCode.AUDIT_UNAVAILABLE)
        event = _result(read_event(receipt.event_id))
        require(type(event) is SecurityEventV2 and event == self._intent_event(item, record.binding, event.occurred_at)
                and event.occurred_at >= datetime.fromisoformat(item['expires_at']), ReasonCode.AUDIT_UNAVAILABLE)
        self._delivery(fact['delivery'], record, read_event)
        return receipt

    def _candidate_fact(self, fact, row, binding, registration, read_event, now):
        require(type(fact) is dict and set(fact) == {'export', 'delivery', 'intent', 'candidate'},
                ReasonCode.UNKNOWN_FIELD)
        require(fact['delivery'] is None and row.delivery_receipt is None and
                (row.retention_candidate is None or row.retention_candidate == fact['candidate']),
                ReasonCode.REPORT_MISMATCH)
        context, stored, stage = self._candidate(row, binding, registration, fact['candidate'], read_event, now)
        item = fact['export']
        require(item['owner_state'] == 'aborted' and item == self._export(
            row, stored, stage.occurred_at, stage, owner_state='aborted'), ReasonCode.REPORT_MISMATCH)
        receipt = AuditReceipt.from_wire(fact['intent'])
        require(receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                ReasonCode.AUDIT_UNAVAILABLE)
        event = _result(read_event(receipt.event_id))
        require(type(event) is SecurityEventV2 and event == self._intent_event(item, binding, event.occurred_at)
                and event.occurred_at >= datetime.fromisoformat(item['expires_at']), ReasonCode.AUDIT_UNAVAILABLE)
        return receipt, context, stored, stage

    def _inventory(self, rows, now):
        require(len(rows) <= self.limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
        expired = []
        for row in rows:
            record, registration, binding = self._record(row, self.read_event, now)
            if record is None:
                if row.retention_candidate is None:
                    continue
                if row.state in ('retiring', 'retired'):
                    _, object_context, stored, _ = self._candidate_fact(
                        row.retention_retirement, row, binding, registration, self.read_event, now)
                    if row.state == 'retired':
                        continue
                    item = row.retention_retirement['export']
                else:
                    object_context, stored, stage = self._candidate(
                        row, binding, registration, row.retention_candidate, self.read_event, now)
                    if now < stage.occurred_at + timedelta(hours=24) or row.state != 'aborted':
                        continue
                    require(row.retention_retirement is None and row.delivery_receipt is None,
                            ReasonCode.REPORT_MISMATCH)
                    state = PrivateObject.objects.filter(object_ref=stored.object_ref).values_list('state', flat=True).first()
                    if state is None:
                        continue  # Without post-write registration an aborted owner can still have a live writer.
                    require(state in ('candidate', 'verified'), ReasonCode.SOURCE_NOT_APPROVED)
                    item = self._export(row, stored, stage.occurred_at, stage)
                expired.append((row, binding, object_context, stored, item))
                continue
            if now < record.report.created_at + timedelta(hours=24):
                continue
            if row.state in ('retiring', 'retired'):
                self._fact(row.retention_retirement, row, record, registration, self.read_event)
                require(row.delivery_receipt == row.retention_retirement['delivery'], ReasonCode.REPORT_MISMATCH)
                if row.state == 'retired':
                    continue
                item = row.retention_retirement['export']
            else:
                require(row.retention_retirement is None, ReasonCode.REPORT_MISMATCH)
                self._delivery(row.delivery_receipt, record, self.read_event)
                item = self._export(row, record.stored, record.report.created_at, registration, delivery=row.delivery_receipt)
            expired.append((row, binding, record.context, record.stored, item))
        return expired

    def preview(self, context):
        """24 hours starts at authenticated generation; unregistered writers are not deletion targets."""
        try:
            now = self._allowed(context)
            rows = list(ExportReport.objects.filter(retention_scope=self.scope_ref).order_by('pk')[
                :self.limits.max_actions + 1])
            return FrozenJSON({'scope_ref': self.scope_ref, 'exports': [item for *_, item in self._inventory(rows, now)]},
                              max_bytes=self.limits.max_json_bytes)
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.AUDIT_UNAVAILABLE
        except (KeyError, TypeError, ValueError):
            code = ReasonCode.REPORT_MISMATCH
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=context.trace_id)

    def initialize(self, context):
        """Explicitly start a new, empty external journal; never done by recovery or HTTP."""
        try:
            self._allowed(context, write=True)
            require(not ExportReport.objects.filter(retention_scope=self.scope_ref,
                retention_retirement__isnull=False).exists(), ReasonCode.SOURCE_NOT_APPROVED)
            document = self.journal.start()
            return FrozenJSON({'scope_ref': self.scope_ref, 'checkpoint_ref': document['audit']['checkpoint_ref']})
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError, KeyError, TypeError, ValueError):
            code = ReasonCode.AUDIT_UNAVAILABLE
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=context.trace_id)

    def _target(self, row, context, stored, *, allow_missing=False):
        require(context.field_ref == 'resources/export' and context.environment is Environment.EVALUATION
                and self.store.environment is Environment.EVALUATION, ReasonCode.SOURCE_NOT_APPROVED)
        identity = content_hash(dict(project=context.project_ref, environment=context.environment,
            object_uuid=context.object_uuid, version=context.object_version, field=context.field_ref))
        require(stored.object_ref == 'private/' + content_hash({'context': identity, 'ciphertext': stored.ciphertext_hash})
                and stored.version == context.object_version, ReasonCode.HASH_MISMATCH)
        require(not ExportReport.objects.filter(private_object_id=stored.object_ref).exclude(pk=row.pk).exists(),
                ReasonCode.SOURCE_NOT_APPROVED)
        private = PrivateObject.objects.select_for_update().filter(object_ref=stored.object_ref).first()
        require(private is not None or allow_missing, ReasonCode.DELIVERY_UNKNOWN)
        if private is not None:
            require((private.context_hash, private.version, private.ciphertext_hash, private.size_bytes) ==
                    (identity, stored.version, stored.ciphertext_hash, stored.size_bytes)
                    and private.state in ('candidate', 'verified', 'published', 'retired'), ReasonCode.REPORT_MISMATCH)
        return private, self.store.root / (stored.object_ref.removeprefix('private/') + '.sealed')

    def _retire(self, fact, binding, context, stored):
        # The signed external intent is durable before this method is called.
        candidate = 'candidate' in fact
        with transaction.atomic():
            row = ExportReport.objects.select_for_update().get(execution_id=binding.execution_id)
            require(row.state in ('retiring', 'retired') and row.retention_retirement == fact,
                    ReasonCode.SOURCE_NOT_APPROVED)
            private, path = self._target(row, context, stored, allow_missing=candidate)
            require(not candidate or private is None or private.state in ('candidate', 'verified', 'retired'),
                    ReasonCode.SOURCE_NOT_APPROVED)
            present = os.path.lexists(path)
            if present:
                self.store._read_file(stored.object_ref, stored.size_bytes, stored.ciphertext_hash)
            else:
                require(candidate or private.state == 'retired', ReasonCode.DELIVERY_UNKNOWN)
            if private is not None:
                private.state = 'retired'
                private.save(update_fields=['state'])
        if candidate:
            require(_result(self.store.retire_candidate(stored, context)) is True, ReasonCode.DELIVERY_UNKNOWN)
        else:
            if present:
                path.unlink()
            directory = os.open(self.store.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        ExportReport.objects.filter(pk=row.pk).update(state='retired')

    def apply(self, approved, context):
        """Re-read the approved inventory; persist intent before any ciphertext deletion."""
        try:
            now = self._allowed(context, write=True)
            require(type(approved) is FrozenJSON, ReasonCode.INVALID_TYPE)
            document = self.journal.read()
            facts = {fact['export']['execution_id']: fact for fact in document['facts']}
            with transaction.atomic():
                rows = list(ExportReport.objects.select_for_update().filter(retention_scope=self.scope_ref).order_by('pk')[
                    :self.limits.max_actions + 1])
                selected = self._inventory(rows, now)
                require(approved == FrozenJSON({'scope_ref': self.scope_ref, 'exports': [item for *_, item in selected]},
                    max_bytes=self.limits.max_json_bytes), ReasonCode.REPORT_MISMATCH)
                for row, binding, object_context, stored, item in selected:
                    private, _ = self._target(row, object_context, stored)
                    require(item['report_hash'] is not None or private.state in ('candidate', 'verified', 'retired'),
                            ReasonCode.SOURCE_NOT_APPROVED)
                    if row.state != 'retiring':
                        require(row.state in ('prepared', 'aborted') and row.execution_id not in facts,
                                ReasonCode.REPORT_MISMATCH)
                        event = self._intent_event(item, binding, now)
                        receipt = _result(self.audit.record(event, Durability.LEDGER_CONFIRMED))
                        require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id
                                and receipt.durability is Durability.LEDGER_CONFIRMED
                                and receipt.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
                        row.retention_retirement = {'export': item, 'delivery': row.delivery_receipt,
                                                    'intent': receipt.to_wire()}
                        if item['report_hash'] is None:
                            row.retention_retirement['candidate'] = row.retention_candidate
                        row.state = 'retiring'
                        row.save(update_fields=['retention_retirement', 'state'])
                    previous = facts.get(row.execution_id)
                    require(previous is None or previous == row.retention_retirement, ReasonCode.REPORT_MISMATCH)
                    facts[row.execution_id] = row.retention_retirement
            if selected:
                self.journal.save(list(facts.values()))
            for row, binding, object_context, stored, _ in selected:
                self._retire(facts[row.execution_id], binding, object_context, stored)
            return tuple(AuditReceipt.from_wire(facts[row.execution_id]['intent']) for row, *_ in selected)
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError, PrivateObject.DoesNotExist, KeyError, TypeError, ValueError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=context.trace_id)

    def replay(self, context, *, recovery_journal):
        """Only the original restored-stage callback may reapply the latest external facts."""
        try:
            now = self._allowed(context, write=True)
            require(recovery_journal.read(context)['state'] == 'restored', ReasonCode.SOURCE_NOT_APPROVED)
            document = self.journal.read()
            bundle = FrozenJSON(document['audit'], max_bytes=self.limits.max_json_bytes)
            sink = self.journal.sink
            if AuthenticatedAuditEntry.objects.filter(chain_identity=sink.chain_identity).count() >= len(document['audit']['entries']):
                receipt = _result(sink.verify_recovery(bundle, self.limits))
            else:
                receipt = _result(sink.restore_recovery(bundle, self.limits, context, journal=recovery_journal))
            for fact in document['facts']:
                with transaction.atomic():
                    row = ExportReport.objects.select_for_update().filter(execution_id=fact['export']['execution_id']).first()
                    if row is None:
                        path = self.store.root / (fact['export']['object_ref'].removeprefix('private/') + '.sealed')
                        require(not PrivateObject.objects.filter(object_ref=fact['export']['object_ref']).exists()
                                and not os.path.lexists(path), ReasonCode.SOURCE_NOT_APPROVED)
                        continue  # A backup older than this export has no matching owner or bytes to resurrect.
                    record, registration, binding = self._record(row, self.read_event, now)
                    states = (fact['export']['owner_state'], 'retiring', 'retired')
                    if record is None:
                        _, object_context, stored, _ = self._candidate_fact(
                            fact, row, binding, registration, self.read_event, now)
                        states += ('preparing',)
                    else:
                        self._fact(fact, row, record, registration, self.read_event)
                        object_context, stored = record.context, record.stored
                    require(row.state in states
                            and (row.retention_retirement is None or row.retention_retirement == fact)
                            and (row.delivery_receipt is None or row.delivery_receipt == fact['delivery']),
                            ReasonCode.REPORT_MISMATCH)
                    private, _ = self._target(row, object_context, stored, allow_missing=record is None)
                    require(record is not None or private is None or private.state in ('candidate', 'verified', 'retired'),
                            ReasonCode.SOURCE_NOT_APPROVED)
                    row.state, row.retention_retirement, row.delivery_receipt = 'retiring', fact, fact['delivery']
                    fields = ['state', 'retention_retirement', 'delivery_receipt']
                    if record is None:
                        row.retention_candidate = fact['candidate']
                        fields.append('retention_candidate')
                    row.save(update_fields=fields)
                self._retire(fact, binding, object_context, stored)
            return receipt
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, OSError, PrivateObject.DoesNotExist, KeyError, TypeError, ValueError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=context.trace_id)

    def verify_retired(self, row, record, binding, audit_events, facts):
        """Read-only owner proof; a retired database flag alone never proves deletion."""
        fact = facts.get(row.execution_id)
        require(self.store is not None and row.state == 'retired' and fact is not None
                and row.retention_retirement == fact and row.delivery_receipt == fact['delivery'],
                ReasonCode.REPORT_MISMATCH)
        read_event = lambda event_id: audit_events[event_id][0]
        registration = self._registration(row, binding, read_event)
        if record is None:
            receipt, object_context, stored, stage = self._candidate_fact(
                fact, row, binding, registration, read_event, self.clock())
            require(audit_events[stage.event_id][1] == AuditReceipt.from_wire(fact['candidate']['registration']),
                    ReasonCode.AUDIT_UNAVAILABLE)
        else:
            receipt = self._fact(fact, row, record, registration, read_event)
            object_context, stored = record.context, record.stored
        require(audit_events[receipt.event_id][1] == receipt, ReasonCode.AUDIT_UNAVAILABLE)
        private = PrivateObject.objects.filter(object_ref=stored.object_ref).first()
        require((private is None and record is None) or (private is not None and private.state == 'retired'),
                ReasonCode.REPORT_MISMATCH)
        if record is None and private is not None:
            require(_result(self.store.inspect_recovery(stored, object_context)) is None, ReasonCode.REPORT_MISMATCH)
        path = self.store.root / (stored.object_ref.removeprefix('private/') + '.sealed')
        require(not os.path.lexists(path), ReasonCode.REPORT_MISMATCH)
