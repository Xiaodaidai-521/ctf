"""Current actors approve exact isolated target plans; source provenance remains separate."""
from dataclasses import replace

from django.db import DatabaseError, connection

from data_security.contracts import (
    ActionPlan, Approval, ContractViolation, Environment, ExecutionBinding, ObjectContext,
    Outlet, ProtectionContext, ProtectionError, Purpose, ReasonCode, Role, SourceTrust,
)
from data_security.contracts.schema import reference, require
from users.models import CTFUser


class ExportPlanOwner:
    def __init__(self, *, write_permission, read_permission, identity, clock, environment, read_approval=None):
        require(environment in (Environment.TEST, Environment.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
        self.write_permission, self.read_permission = write_permission, read_permission
        self.identity, self.clock, self.environment = identity, clock, environment
        self.read_approval = read_approval

    def _target(self, plan, binding, context):
        require(type(plan) is ActionPlan and type(binding) is ExecutionBinding and
                type(context) is ObjectContext, ReasonCode.INVALID_TYPE)
        require(binding.environment == self.environment.value and context.environment is self.environment and
                plan.source.source_trust is SourceTrust.SYNTHETIC and
                plan.source.source_environment == binding.environment and
                plan.source.source_domain == binding.domain_ref and
                plan.source.provenance_ref is not None and plan.source.approval_basis_ref is not None,
                ReasonCode.SOURCE_NOT_APPROVED)
        require((plan.asset_version, plan.scope, plan.policy_binding) ==
                (binding.asset_version, binding.scope, binding.policy_binding) and
                context.object_version == binding.asset_version and
                context.authorization_ref == binding.authorization_id, ReasonCode.REPORT_MISMATCH)

    def _actor(self, user, capability=None):
        require(user.is_authenticated, ReasonCode.AUTHORIZATION_DENIED)
        actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
        require(actor is not None and (capability is None or actor.has_perm(capability)),
                ReasonCode.AUTHORIZATION_DENIED)
        return actor

    def manage(self, *, user, operation, plan, binding, context, requester=None):
        """Trusted owner inputs only; approving a target does not approve its source or reserve quota."""
        trace = 'export-plan/manage'
        try:
            self._target(plan, binding, context)
            require(operation in ('approve', 'revoke'), ReasonCode.INVALID_VALUE)
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            capability = 'add' if operation == 'approve' else 'change'
            actor = self._actor(user, 'security_policies.' + capability + '_exportplanapproval')
            if operation == 'approve':
                require(plan.approval is None and requester is not None, ReasonCode.INVALID_VALUE)
                applicant = self._actor(requester)
                require(binding.subject_ref == 'user/' + str(applicant.pk) and applicant.pk != actor.pk,
                        ReasonCode.AUTHORIZATION_DENIED)
                now = self.clock()
                require(plan.created_at <= now < min(plan.expires_at, binding.expires_at),
                        ReasonCode.AUTHORIZATION_EXPIRED)
                require(not plan.unresolved, ReasonCode.SCOPE_INCOMPLETE)
                approval = Approval(schema_version=Approval.SCHEMA, approval_ref='plan-approval/' + self.identity(),
                    requested_by=binding.subject_ref, approved_by='user/' + str(actor.pk),
                    approved_at=now, content_hash=plan.plan_hash)
                plan = replace(plan, approval=approval)
            else:
                require(plan.approval is not None and requester is None, ReasonCode.INVALID_VALUE)
            trace = plan.approval.approval_ref
            event_id = trace + '/approve' if operation == 'approve' else 'plan-revoke/' + self.identity()
            receipt = self.write_permission(operation=operation, plan=plan, binding=binding, context=context,
                actor_ref='user/' + str(actor.pk), event_id=event_id)
            return receipt if isinstance(receipt, ProtectionError) else (plan, receipt)
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=trace)

    def reconcile(self, *, user, approval_ref, plan, binding, context):
        """Recover the original approval after unknown, never issue another approval."""
        try:
            self._target(plan, binding, context)
            reference(approval_ref)
            require(plan.approval is None and self.read_approval is not None, ReasonCode.INVALID_VALUE)
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            self._actor(user, 'security_policies.add_exportplanapproval')
            approval = self.read_approval(approval_ref, plan, binding, context)
            return approval if isinstance(approval, ProtectionError) else replace(plan, approval=approval)
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='export-plan/reconcile')

    def authorize(self, *, user, plan, binding, context):
        """Re-read the active requester and exact approval, including after the flow's report lock."""
        try:
            self._target(plan, binding, context)
            actor = self._actor(user)
            require(binding.subject_ref == 'user/' + str(actor.pk) and plan.approval is not None,
                    ReasonCode.AUTHORIZATION_DENIED)
            require(not plan.unresolved, ReasonCode.SCOPE_INCOMPLETE)
            principal = ProtectionContext(schema_version=ProtectionContext.SCHEMA,
                actor_ref=binding.subject_ref, authorization_ref=binding.authorization_id,
                scope_refs=(context.field_ref,), environment=self.environment, domain=binding.domain_ref,
                outlet=Outlet.EXPORT, purpose=Purpose.DELIVERY, role=Role(actor.role),
                object_ref=context.object_uuid, object_version=context.object_version,
                source_ref=None, source_version=None, source_hash=None, trace_id=binding.execution_id)
            return self.read_permission(principal, plan, binding, context)
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='export-plan/authorize')
