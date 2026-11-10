"""Exact target-plan approval state; no risk, quota, source or private-file writer."""
from django.db import DatabaseError, transaction

from data_security.contracts import (
    Approval, AuditReceipt, ContractViolation, Durability, EventKind, Outcome, ProtectionError,
    ReasonCode, SecurityEventV2, content_hash,
)
from data_security.contracts.schema import require
from .models import ExportPlanApproval


class DjangoExportPlanApprovals:
    def __init__(self, *, record_event, clock, read_event=None):
        self.record_event, self.clock = record_event, clock
        self.read_event = read_event

    def write(self, *, operation, plan, binding, context, actor_ref, event_id):
        reference = plan.approval.approval_ref
        values = dict(plan_hash=plan.plan_hash, binding_hash=content_hash(binding),
                      context_hash=content_hash(context), document=plan.approval.to_wire(),
                      expires_at=min(plan.expires_at, binding.expires_at))
        try:
            with transaction.atomic():
                if operation == 'approve':
                    permission = ExportPlanApproval.objects.create(approval_ref=reference, **values)
                else:
                    permission = ExportPlanApproval.objects.select_for_update().filter(approval_ref=reference).first()
                    require(permission is not None and all(getattr(permission, k) == v for k, v in values.items()),
                            ReasonCode.AUTHORIZATION_DENIED)
                    if permission.revoked_at is None:
                        permission.revoked_at = self.clock()
                        permission.save(update_fields=['revoked_at'])
                metadata = dict(values, approval_ref=reference, revoked_at=permission.revoked_at)
                event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                    event_id=event_id, kind=EventKind.AUTHORIZATION, actor_ref=actor_ref,
                    object_ref=reference, object_version='1', outcome=Outcome.SUCCEEDED,
                    occurred_at=self.clock(), counts=(('processed', 1),), policy_binding=binding.policy_binding,
                    algorithm_versions=('export-plan-approval.v1', operation), key_versions=(),
                    correlation_ref=binding.execution_id, reason=None,
                    evidence_hashes=(('report', content_hash(metadata)),))
                receipt = self.record_event(event, Durability.LEDGER_CONFIRMED)
                if isinstance(receipt, ProtectionError):
                    require(False, receipt.code)
                require(type(receipt) is AuditReceipt and receipt.event_id == event_id and
                        receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                        ReasonCode.AUDIT_UNAVAILABLE)
            return receipt
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=reference)

    def read_approval(self, approval_ref, plan, binding, context):
        try:
            with transaction.atomic():
                permission = ExportPlanApproval.objects.select_for_update().filter(approval_ref=approval_ref).first()
                require(permission is not None and permission.revoked_at is None, ReasonCode.AUTHORIZATION_DENIED)
                approval = Approval.from_wire(permission.document)
                values = dict(plan_hash=plan.plan_hash, binding_hash=content_hash(binding),
                              context_hash=content_hash(context), document=approval.to_wire(),
                              expires_at=min(plan.expires_at, binding.expires_at))
                require(all(getattr(permission, k) == v for k, v in values.items()) and
                        approval.approval_ref == approval_ref and approval.content_hash == plan.plan_hash and
                        approval.requested_by == binding.subject_ref, ReasonCode.AUTHORIZATION_DENIED)
                require(self.read_event is not None, ReasonCode.AUDIT_UNAVAILABLE)
                event = self.read_event(approval_ref + '/approve')
                if isinstance(event, ProtectionError):
                    require(False, event.code)
                require(type(event) is SecurityEventV2, ReasonCode.AUDIT_UNAVAILABLE)
                expected = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                    event_id=approval_ref + '/approve', kind=EventKind.AUTHORIZATION, actor_ref=approval.approved_by,
                    object_ref=approval_ref, object_version='1', outcome=Outcome.SUCCEEDED,
                    occurred_at=event.occurred_at, counts=(('processed', 1),), policy_binding=binding.policy_binding,
                    algorithm_versions=('export-plan-approval.v1', 'approve'), key_versions=(),
                    correlation_ref=binding.execution_id, reason=None,
                    evidence_hashes=(('report', content_hash(dict(values, approval_ref=approval_ref, revoked_at=None))),))
                require(event == expected, ReasonCode.REPORT_MISMATCH)
                require(self.clock() < permission.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
            return approval
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=approval_ref)

    def authorize(self, principal, plan, binding, context):
        try:
            with transaction.atomic():
                permission = ExportPlanApproval.objects.select_for_update().filter(
                    approval_ref=plan.approval.approval_ref).first()
                require(permission is not None and permission.revoked_at is None and
                        permission.plan_hash == plan.plan_hash and permission.binding_hash == content_hash(binding) and
                        permission.context_hash == content_hash(context) and
                        permission.document == plan.approval.to_wire(), ReasonCode.AUTHORIZATION_DENIED)
                # Read the clock after lock waiting, not before the approval row is locked.
                require(self.clock() < permission.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
            return principal
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=binding.execution_id)
