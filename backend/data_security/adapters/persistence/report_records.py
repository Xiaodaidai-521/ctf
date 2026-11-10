"""Immutable owner report storage. A loaded record is not proof of delivery.

The caller must verify its MAC against owner bindings and recheck current policy,
authorization and quota. This adapter neither signs nor publishes anything.
"""
from datetime import datetime
import hashlib
import json

from django.db import DatabaseError, IntegrityError, connection, transaction

from data_security.contracts import (
    ActionPlan, ContractViolation, Coverage, DeliveryReceipt, Durability, Environment, ExecutionBinding, MaskReport,
    ObjectContext, Outcome, PolicyBinding, ProtectionError, ReasonCode, ReportProof,
    ReportRecord, ScanState, SourcePlanBinding, StoredObject, Unresolved, content_hash,
)
from data_security.contracts.schema import MAX_WIRE_BYTES, require
from data_security.adapters.persistence.models import ExportReport


class DjangoReportRepository:
    def __init__(self, *, environment, lifecycle=None):
        require(type(environment) is Environment and environment is not Environment.PRODUCTION,
                ReasonCode.SOURCE_NOT_APPROVED)
        self.environment, self.lifecycle = environment, lifecycle

    def begin(self, plan, binding, context):
        """Only the creator may prepare; the flow commits this short UoW first."""
        try:
            require(connection.in_atomic_block, ReasonCode.AUTHORIZATION_DENIED)
            require(binding.environment == self.environment.value and context.environment is self.environment,
                    ReasonCode.SOURCE_NOT_APPROVED)
            require(plan.asset_version == binding.asset_version == context.object_version and
                    plan.policy_binding == binding.policy_binding and plan.scope == binding.scope and
                    context.authorization_ref == binding.authorization_id, ReasonCode.REPORT_MISMATCH)
            intent = content_hash({'binding': binding, 'plan': plan, 'context': context})
            row, created = ExportReport.objects.get_or_create(idempotency_key=binding.idempotency_key,
                defaults=dict(execution_id=binding.execution_id, binding_hash=content_hash(binding),
                              binding_document=binding.to_wire(), intent_hash=intent, state='preparing'))
            row = ExportReport.objects.select_for_update().get(pk=row.pk)
            require(row.binding_hash == content_hash(binding) and row.execution_id == binding.execution_id,
                    ReasonCode.IDEMPOTENCY_CONFLICT)
            # Rows prepared before the fence existed retain their original document.
            recorded_intent = row.intent_hash
            if not recorded_intent:
                # Stored JSON has wire lists; M0 canonicalization takes DTOs/tuples.
                encoded = json.dumps({key: row.document[key] for key in ('binding', 'plan', 'context')},
                    sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
                recorded_intent = hashlib.sha256(encoded).hexdigest()
            require(recorded_intent == intent, ReasonCode.IDEMPOTENCY_CONFLICT)
            require(row.state in ('preparing', 'prepared'), ReasonCode.AUTHORIZATION_DENIED)
            if created and self.lifecycle is not None:
                receipt = self.lifecycle.register(binding)
                row.retention_scope = self.lifecycle.scope_ref
                row.retention_registration = receipt.to_wire()
                row.save(update_fields=['retention_scope', 'retention_registration'])
            return created
        except ContractViolation as error:
            code = error.code
        except IntegrityError:
            code = ReasonCode.IDEMPOTENCY_CONFLICT
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        except (KeyError, TypeError, ValueError):
            code = ReasonCode.REPORT_MISMATCH
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=binding.execution_id)

    def load_binding(self, execution_id):
        """Resolve a retained server intent; absence is unknown, never zero delivery."""
        try:
            row = ExportReport.objects.filter(execution_id=execution_id).first()
            require(row is not None, ReasonCode.DELIVERY_UNKNOWN)
            document = row.binding_document
            if document is None and row.document is not None:
                document = row.document['binding']
            require(document is not None, ReasonCode.DELIVERY_UNKNOWN)
            binding = ExecutionBinding.from_wire(document)
            require((binding.execution_id, binding.idempotency_key, content_hash(binding)) ==
                    (row.execution_id, row.idempotency_key, row.binding_hash), ReasonCode.REPORT_MISMATCH)
            require(binding.environment == self.environment.value, ReasonCode.SOURCE_NOT_APPROVED)
            return binding
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        except (KeyError, TypeError, ValueError):
            code = ReasonCode.REPORT_MISMATCH
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='reports/binding')

    def abort(self, binding):
        """Fence preparation/publication, or return the prior logical delivery.

        The caller owns the UoW and any quota operation. Absence is never evidence
        of zero delivery, and this method does not release or reconcile a hold.
        """
        try:
            require(connection.in_atomic_block, ReasonCode.AUTHORIZATION_DENIED)
            require(binding.environment == self.environment.value, ReasonCode.SOURCE_NOT_APPROVED)
            row = ExportReport.objects.select_for_update().filter(idempotency_key=binding.idempotency_key).first()
            require(row is not None, ReasonCode.REPORT_MISMATCH)
            require(row.binding_hash == content_hash(binding) and row.execution_id == binding.execution_id,
                    ReasonCode.IDEMPOTENCY_CONFLICT)
            require(row.state in ('preparing', 'prepared', 'aborted'), ReasonCode.REPORT_MISMATCH)
            if row.state == 'prepared':
                previous = self._delivery(binding, locked=True)
                if previous is not None:
                    return previous
            else:
                require(row.delivery_receipt is None, ReasonCode.REPORT_MISMATCH)
            row.state = 'aborted'
            row.save(update_fields=['state'])
            return None
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=binding.execution_id)

    def put(self, record):
        return self._run(record.binding, record=record)

    def read(self, binding):
        return self._run(binding)

    def delivery(self, binding):
        return self._delivery(binding)

    def lock_delivery(self, binding, record_hash):
        return self._delivery(binding, record_hash=record_hash, locked=True)

    def record_delivery(self, receipt):
        return self._delivery(receipt.binding, receipt=receipt, locked=True)

    def _delivery(self, binding, *, record_hash=None, receipt=None, locked=False):
        try:
            require(binding.environment == self.environment.value, ReasonCode.SOURCE_NOT_APPROVED)
            # The flow owns the outer transaction. A lock in an adapter-only
            # savepoint would expire before publication/quota/audit can use it.
            require(not locked or connection.in_atomic_block, ReasonCode.AUTHORIZATION_DENIED)
            query = ExportReport.objects.select_for_update() if locked else ExportReport.objects
            row = query.filter(idempotency_key=binding.idempotency_key).first()
            require(row is not None, ReasonCode.REPORT_MISMATCH)
            require(row.binding_hash == content_hash(binding) and row.execution_id == binding.execution_id,
                    ReasonCode.IDEMPOTENCY_CONFLICT)
            require(row.state == 'prepared', ReasonCode.AUTHORIZATION_DENIED)
            encoded = json.dumps(row.document, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=False, allow_nan=False).encode('utf-8')
            require(len(encoded) <= MAX_WIRE_BYTES, ReasonCode.LIMIT_EXCEEDED)
            require(hashlib.sha256(encoded).hexdigest() == row.document_hash and
                    (record_hash is None or record_hash == row.document_hash), ReasonCode.REPORT_MISMATCH)
            previous = None
            if row.delivery_receipt is not None:
                try:
                    previous = DeliveryReceipt.from_wire(row.delivery_receipt)
                except ContractViolation:
                    raise ContractViolation(ReasonCode.REPORT_MISMATCH) from None
                require(previous.to_wire() == row.delivery_receipt, ReasonCode.REPORT_MISMATCH)
            for value in (previous, receipt):
                if value is not None:
                    require(value.binding == binding, ReasonCode.IDEMPOTENCY_CONFLICT)
                    require(value.outcome is Outcome.SUCCEEDED and
                            value.audit.durability is Durability.LEDGER_CONFIRMED and
                            value.audit.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
            if receipt is None:
                return previous
            if previous is not None:
                require(previous == receipt, ReasonCode.IDEMPOTENCY_CONFLICT)
                return previous
            row.delivery_receipt = receipt.to_wire()
            row.save(update_fields=['delivery_receipt'])
            return receipt
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        except (KeyError, TypeError, ValueError):
            code = ReasonCode.REPORT_MISMATCH
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='reports/delivery')

    def _run(self, binding, *, record=None):
        try:
            require(binding.environment == self.environment.value, ReasonCode.SOURCE_NOT_APPROVED)
            binding_hash = content_hash(binding)
            if record is not None:
                document = record.to_wire(include_payload=True)
            else:
                row = ExportReport.objects.filter(idempotency_key=binding.idempotency_key).first()
                if row is None:
                    return None
                require(row.binding_hash == binding_hash and row.execution_id == binding.execution_id,
                        ReasonCode.IDEMPOTENCY_CONFLICT)
                require(row.state in ('preparing', 'prepared', 'aborted', 'retiring', 'retired'),
                        ReasonCode.REPORT_MISMATCH)
                if row.document is None:
                    require((row.state in ('preparing', 'aborted') or
                             (row.state in ('retiring', 'retired') and row.retention_scope is not None
                              and row.retention_candidate is not None and row.retention_retirement is not None))
                            and row.private_object_id is None and not row.document_hash, ReasonCode.REPORT_MISMATCH)
                    return None
                document = row.document
            # JSONField contains wire lists, not DTO tuples. Encode that JSON
            # directly with the same canonical ordering/UTF-8 rules as M0.
            encoded = json.dumps(document, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=False, allow_nan=False).encode('utf-8')
            require(len(encoded) <= MAX_WIRE_BYTES, ReasonCode.LIMIT_EXCEEDED)
            document_hash = hashlib.sha256(encoded).hexdigest()
            if record is not None:
                intent = content_hash({'binding': binding, 'plan': record.plan, 'context': record.context})
                with transaction.atomic():
                    row, _ = ExportReport.objects.get_or_create(idempotency_key=binding.idempotency_key,
                        defaults=dict(execution_id=binding.execution_id, binding_hash=binding_hash,
                            binding_document=binding.to_wire(), private_object_id=record.stored.object_ref, document=document,
                            document_hash=document_hash, intent_hash=intent))
                    row = ExportReport.objects.select_for_update().get(pk=row.pk)
                    require(row.binding_hash == binding_hash and row.execution_id == binding.execution_id,
                            ReasonCode.IDEMPOTENCY_CONFLICT)
                    require(row.state in ('preparing', 'prepared'), ReasonCode.AUTHORIZATION_DENIED)
                    if row.retention_candidate is not None:
                        candidate = row.retention_candidate
                        require(candidate['intent_hash'] == intent and candidate['context'] == record.context.to_wire()
                                and candidate['stored'] == dict(record.stored.to_wire(), state='candidate'),
                                ReasonCode.REPORT_MISMATCH)
                    if row.state == 'preparing':
                        require(row.intent_hash == intent, ReasonCode.IDEMPOTENCY_CONFLICT)
                        require(row.document is None and row.private_object_id is None and
                                not row.document_hash and row.delivery_receipt is None, ReasonCode.REPORT_MISMATCH)
                        row.document, row.document_hash = document, document_hash
                        row.private_object_id, row.state = record.stored.object_ref, 'prepared'
                        row.save(update_fields=['document', 'document_hash', 'private_object', 'state'])
                    require(row.private_object_id == record.stored.object_ref and row.document == document and
                            row.document_hash == document_hash, ReasonCode.IDEMPOTENCY_CONFLICT)
                return record

            require(document_hash == row.document_hash, ReasonCode.REPORT_MISMATCH)
            # Only this DB boundary reconstructs SERVER_ONLY values; the public
            # wire decoder remains closed. Nested DTOs validate their own fields.
            values = dict(document['report'])
            values['source'] = SourcePlanBinding.from_wire(values['source'])
            values['policy_binding'] = PolicyBinding.from_wire(values['policy_binding'])
            for field in ('coverage', 'rescan_coverage'):
                values[field] = Coverage.from_wire(values[field])
            for field in ('excluded', 'unresolved'):
                values[field] = tuple(Unresolved.from_wire(item) for item in values[field])
            values['algorithm_versions'] = tuple(values['algorithm_versions'])
            values['rescan_state'] = ScanState(values['rescan_state'])
            values['outcome'] = Outcome(values['outcome'])
            values['created_at'] = datetime.fromisoformat(values['created_at'])
            context_values = dict(document['context'])
            context_values['environment'] = Environment(context_values['environment'])
            loaded = dict(document)
            loaded.update(binding=ExecutionBinding.from_wire(document['binding']),
                plan=ActionPlan.from_wire(document['plan']), context=ObjectContext(**context_values),
                stored=StoredObject.from_wire(document['stored']), report=MaskReport(**values),
                proof=ReportProof.from_wire(document['proof']))
            result = ReportRecord(**loaded)
            require(result.binding == binding and result.stored.object_ref == row.private_object_id,
                    ReasonCode.REPORT_MISMATCH)
            require(result.to_wire(include_payload=True) == document, ReasonCode.REPORT_MISMATCH)
            return result
        except ContractViolation as error:
            code = error.code
        except IntegrityError:
            code = ReasonCode.IDEMPOTENCY_CONFLICT
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        except (KeyError, TypeError, ValueError):
            code = ReasonCode.REPORT_MISMATCH
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='reports/record')
