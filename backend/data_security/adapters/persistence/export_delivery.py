"""Re-fetch complete owner inputs and delegate delivery to the injected M4 flow."""
from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import UUID

from django.db import DatabaseError, connection

from data_security.contracts import (
    ActionPlan, ContractViolation, Environment, ExecutionBinding, FrozenJSON, ObjectContext,
    ProtectionError, ReasonCode, Unit,
)
from data_security.contracts.schema import require
from export_risk.column_authority import ColumnRiskSupplier, decode_request
from export_risk.contracts import ExportRequestSnapshot


@dataclass(frozen=True, slots=True, repr=False)
class OwnedResourceExport:
    source_ref: str
    source_hash: str
    source_plan: ActionPlan
    permission_ref: str
    request: ExportRequestSnapshot
    plan: ActionPlan
    binding: ExecutionBinding
    context: ObjectContext
    risk: ColumnRiskSupplier


class DjangoResourceExports:
    def __init__(self, *, sources, risks, targets, flow_factory, clock, ttl_seconds, identity, uploads):
        self.sources, self.risks, self.targets = sources, risks, targets
        self.flow_factory, self.clock, self.ttl_seconds = flow_factory, clock, ttl_seconds
        self.identity, self.uploads = identity, uploads

    def grant_risk(self, *, user, source_ref, expires_at):
        retained = self.sources.inspect(user=user, source_ref=source_ref)
        if isinstance(retained, ProtectionError):
            return retained
        row, document, plan = retained
        values = document.to_value()
        try:
            return self.risks.grant(user=user, source_ref=source_ref, source_hash=row.document_hash,
                request=decode_request(values['request']), scope=plan.scope, domain_ref=plan.source.source_domain,
                policy_binding=plan.policy_binding, risk_inputs=FrozenJSON(values['risk_inputs']), expires_at=expires_at)
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, source_ref)

    def _load(self, *, user, source_ref, permission_ref, risk_permission_ref=None):
        require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
        retained = self.sources.load(user=user, source_ref=source_ref, permission_ref=permission_ref)
        if isinstance(retained, ProtectionError):
            return retained
        row, document, plan, source_deadline = retained
        values = document.to_value()
        request = decode_request(values['request'])
        if row.execution_document is not None:
            previous = row.execution_document['risk_permission_ref']
            require(risk_permission_ref is None or risk_permission_ref == previous, ReasonCode.IDEMPOTENCY_CONFLICT)
            risk_permission_ref = previous
        require(risk_permission_ref is not None, ReasonCode.AUTHORIZATION_DENIED)
        risk = self.risks.load(user=user, permission_ref=risk_permission_ref, source_ref=source_ref,
            source_hash=row.document_hash, request=request, scope=plan.scope, domain_ref=plan.source.source_domain,
            policy_binding=plan.policy_binding, risk_inputs=FrozenJSON(values['risk_inputs']))
        if isinstance(risk, ProtectionError):
            return risk
        return row, request, plan, risk, source_deadline, risk_permission_ref

    def admit(self, *, user, source_ref, permission_ref, risk_permission_ref):
        """Expose the real pending decision without a reservation, claim or source open."""
        try:
            loaded = self._load(user=user, source_ref=source_ref, permission_ref=permission_ref,
                                risk_permission_ref=risk_permission_ref)
            return loaded if isinstance(loaded, ProtectionError) else loaded[3].admit()
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, source_ref)

    @staticmethod
    def _binding_context(row, plan):
        document = row.execution_document
        require(type(document) is dict and set(document) == {'binding', 'context', 'risk_permission_ref'},
                ReasonCode.REPORT_MISMATCH)
        binding = ExecutionBinding.from_wire(document['binding'])
        value = document['context']
        context = ObjectContext(schema_version=value['schema_version'], project_ref=value['project_ref'],
            environment=Environment(value['environment']), object_uuid=value['object_uuid'],
            object_version=value['object_version'], field_ref=value['field_ref'],
            authorization_ref=value['authorization_ref'])
        base = 'resource-export/' + row.source_ref.split('/', 1)[1]
        request = row.document['request']
        require((binding.idempotency_key, binding.execution_id, binding.authorization_id, binding.reservation_id,
                 binding.request_id, binding.request_fingerprint, binding.subject_ref, binding.asset_version,
                 binding.quantity, binding.quantity_unit, binding.domain_ref, binding.environment, binding.scope,
                 binding.policy_binding, context.project_ref, context.environment, context.object_uuid,
                 context.object_version, context.field_ref, context.authorization_ref) ==
                (base + '/idempotency', base + '/execution', base + '/authorization', base + '/reservation',
                 request['request_id'], request['request_fingerprint'], request['subject_id'], request['asset_version'],
                 request['record_count'], Unit.RECORD, plan.source.source_domain, 'evaluation', plan.scope,
                 plan.policy_binding, row.document['context']['project_ref'], Environment.EVALUATION,
                 str(UUID(row.source_ref.split('/', 1)[1])), plan.asset_version, 'resources/export', binding.authorization_id),
                ReasonCode.REPORT_MISMATCH)
        require(binding.expires_at <= row.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
        return binding, context

    def bind(self, *, user, source_ref, permission_ref, risk_permission_ref):
        """Retain one complete execution only after genuine original risk admission."""
        try:
            loaded = self._load(user=user, source_ref=source_ref, permission_ref=permission_ref,
                                risk_permission_ref=risk_permission_ref)
            if isinstance(loaded, ProtectionError):
                return loaded
            row, request, plan, risk, source_deadline, risk_ref = loaded
            if row.execution_document is not None:
                return self._binding_context(row, plan)[0]
            admitted = risk.admit()
            if isinstance(admitted, ProtectionError):
                return admitted
            _, decision_id, blocker = admitted
            require(blocker is None, ReasonCode.AUTHORIZATION_DENIED)
            base = 'resource-export/' + source_ref.split('/', 1)[1]
            binding = ExecutionBinding(schema_version=ExecutionBinding.SCHEMA,
                idempotency_key=base + '/idempotency', request_fingerprint=request.request_fingerprint,
                request_id=request.request_id, authorization_id=base + '/authorization', decision_id=decision_id,
                asset_version=request.asset_version, execution_id=base + '/execution', reservation_id=base + '/reservation',
                subject_ref=request.subject_id, domain_ref=plan.source.source_domain, environment='evaluation',
                scope=plan.scope, quantity=request.record_count, quantity_unit=Unit.RECORD,
                expires_at=min(plan.expires_at, source_deadline, risk.active_until,
                               self.clock() + timedelta(seconds=self.ttl_seconds)), policy_binding=plan.policy_binding)
            context = ObjectContext(schema_version=ObjectContext.SCHEMA,
                project_ref=row.document['context']['project_ref'], environment=Environment.EVALUATION,
                object_uuid=str(UUID(source_ref.split('/', 1)[1])), object_version=plan.asset_version,
                field_ref='resources/export', authorization_ref=binding.authorization_id)
            return self.sources.retain_execution(user=user, source_ref=source_ref, permission_ref=permission_ref,
                risk_permission_ref=risk_ref, binding=binding, context=context)
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, source_ref)

    def approve_target(self, *, user, source_ref, requester):
        trace = source_ref
        try:
            retained = self.sources.target(user=user, source_ref=source_ref)
            if isinstance(retained, ProtectionError):
                return retained
            row, plan = retained
            binding, context = self._binding_context(row, plan)
            if row.target_approval_ref:
                return self.targets.reconcile(user=user, approval_ref=row.target_approval_ref,
                    plan=plan, binding=binding, context=context)
            result = self.targets.manage(user=user, operation='approve', requester=requester,
                                         plan=plan, binding=binding, context=context)
            if isinstance(result, ProtectionError):
                return result
            approved, _ = result
            trace = approved.approval.approval_ref
            retained = self.sources.retain_target(user=user, source_ref=source_ref, approval_ref=trace)
            return replace(retained, trace_id=trace) if isinstance(retained, ProtectionError) else approved
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, trace)

    def reconcile_target(self, *, user, source_ref, approval_ref):
        try:
            retained = self.sources.target(user=user, source_ref=source_ref)
            if isinstance(retained, ProtectionError):
                return retained
            row, plan = retained
            binding, context = self._binding_context(row, plan)
            approved = self.targets.reconcile(user=user, approval_ref=approval_ref,
                                              plan=plan, binding=binding, context=context)
            if isinstance(approved, ProtectionError):
                return approved
            reference = self.sources.retain_target(user=user, source_ref=source_ref, approval_ref=approval_ref)
            return reference if isinstance(reference, ProtectionError) else approved
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, source_ref)

    def _bound(self, *, user, source_ref, permission_ref):
        loaded = self._load(user=user, source_ref=source_ref, permission_ref=permission_ref)
        if isinstance(loaded, ProtectionError):
            return loaded
        row, request, plan, risk, _, _ = loaded
        binding, context = self._binding_context(row, plan)
        require(row.target_approval_ref, ReasonCode.POLICY_NOT_APPROVED)
        approval = self.targets.read_approval(row.target_approval_ref, plan, binding, context)
        if isinstance(approval, ProtectionError):
            return approval
        return OwnedResourceExport(source_ref=source_ref, source_hash=row.document_hash,
            source_plan=plan, permission_ref=permission_ref, request=request,
            plan=replace(plan, approval=approval), binding=binding, context=context, risk=risk)

    def execute(self, *, user, source_ref, permission_ref):
        try:
            owned = self._bound(user=user, source_ref=source_ref, permission_ref=permission_ref)
            if isinstance(owned, ProtectionError):
                return owned
            flow = self.flow_factory(user, owned)
            owner = flow.authorize(owned.plan, owned.binding, owned.context)
            if isinstance(owner, ProtectionError):
                return owner
            return flow.execute(owned.plan, owned.binding, owner)
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, source_ref)

    def open_delivery(self, *, user, source_ref, permission_ref):
        try:
            owned = self._bound(user=user, source_ref=source_ref, permission_ref=permission_ref)
            if isinstance(owned, ProtectionError):
                return owned
            return self.flow_factory(user, owned).open_delivery(owned.binding, attempt_ref='read/' + self.identity())
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, source_ref)

    def describe(self, *, user, source_ref, permission_ref):
        """Read the same authorized owner binding and authenticate its retained output."""
        try:
            owned = self._bound(user=user, source_ref=source_ref, permission_ref=permission_ref)
            if isinstance(owned, ProtectionError):
                return owned
            flow = self.flow_factory(user, owned)
            record = flow.reports.read(owned.binding)
            if isinstance(record, ProtectionError):
                return record
            result = {'state': 'ready' if record is None else 'unknown',
                'can_execute': record is None, 'can_download': False,
                'protection': {'redaction': 'unknown', 'storage': 'unknown'},
                'expires_at': owned.binding.expires_at.isoformat(), 'network_delivery_confirmed': False}
            if record is not None:
                inspected = flow.inspect_delivery(owned.binding)
                if not isinstance(inspected, ProtectionError):
                    _, receipt, _, _envelope, _evidence = inspected
                    result.update(state='generated', can_download=True,
                        delivered_records=receipt.delivered_records,
                        protection={'redaction': 'completed', 'storage': 'encrypted'})
            return result
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, source_ref)

    @staticmethod
    def _failure(error, trace):
        code = (error.code if isinstance(error, ContractViolation) else
                ReasonCode.DELIVERY_UNKNOWN if isinstance(error, DatabaseError) else ReasonCode.REPORT_MISMATCH)
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=trace)
