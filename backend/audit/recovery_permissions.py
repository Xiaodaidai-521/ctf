"""Current Django actors own recovery permission management, not the quota writer."""
from datetime import datetime

from django.db import DatabaseError

from data_security.contracts import (
    ContractViolation, Environment, ExecutionBinding, Outlet, ProtectionContext,
    ProtectionError, Purpose, ReasonCode, Role,
)
from data_security.contracts.schema import reference, require
from users.models import CTFUser


class RecoveryPermissionOwner:
    def __init__(self, *, write_permission, read_permission, identity, clock, environment):
        require(environment in (Environment.TEST, Environment.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
        self.write_permission, self.read_permission = write_permission, read_permission
        self.identity, self.clock, self.environment = identity, clock, environment

    def _principal(self, user, binding, permission=None):
        require(type(binding) is ExecutionBinding and binding.environment == self.environment.value,
                ReasonCode.SOURCE_NOT_APPROVED)
        require(user.is_authenticated, ReasonCode.AUTHORIZATION_DENIED)
        actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
        require(actor is not None and (permission is None or actor.has_perm(permission)),
                ReasonCode.AUTHORIZATION_DENIED)
        return ProtectionContext(schema_version=ProtectionContext.SCHEMA,
            actor_ref='user/' + str(actor.pk), authorization_ref='recovery-owner/user-' + str(actor.pk),
            scope_refs=(binding.reservation_id,), environment=self.environment, domain=binding.domain_ref,
            outlet=Outlet.AUDIT, purpose=Purpose.SECURITY_AUDIT, role=Role(actor.role),
            object_ref=binding.execution_id, object_version=binding.asset_version,
            source_ref=None, source_version=None, source_hash=None, trace_id=binding.execution_id)

    def manage(self, *, user, binding, operation, authorization_ref=None,
               grantee_id=None, expires_at=None, allow_release=False, allow_reconcile=False):
        """Internal typed request; this neither assigns Django permissions nor opens an HTTP route."""
        trace = 'recovery-permission/manage'
        try:
            require(operation in ('grant', 'revoke'), ReasonCode.AUTHORIZATION_DENIED)
            capability = 'add' if operation == 'grant' else 'change'
            principal = self._principal(user, binding, 'security_policies.' + capability + '_recoverypermission')
            grant = None
            if operation == 'grant':
                require(authorization_ref is None and type(grantee_id) is int and grantee_id > 0 and
                        type(expires_at) is datetime and expires_at.utcoffset() is not None and
                        expires_at > self.clock() and type(allow_release) is bool and
                        type(allow_reconcile) is bool and (allow_release or allow_reconcile),
                        ReasonCode.INVALID_VALUE)
                require(CTFUser.objects.filter(pk=grantee_id, is_active=True).exists(),
                        ReasonCode.AUTHORIZATION_DENIED)
                authorization_ref = 'recovery/' + self.identity()
                grant = dict(actor_ref='user/' + str(grantee_id), expires_at=expires_at,
                    allow_release=allow_release, allow_reconcile=allow_reconcile)
            else:
                reference(authorization_ref, maximum=160)
                require(grantee_id is None and expires_at is None and
                        allow_release is False and allow_reconcile is False, ReasonCode.INVALID_VALUE)
            trace = authorization_ref
            event_id = authorization_ref + '/grant' if operation == 'grant' else 'recovery/revoke/' + self.identity()
            receipt = self.write_permission(operation=operation, binding=binding, principal=principal,
                authorization_ref=authorization_ref, event_id=event_id, grant=grant)
            if isinstance(receipt, ProtectionError):
                return receipt
            return authorization_ref, receipt
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=trace)

    def authorize(self, *, user, binding, operation, authorization_ref):
        """Called inside the flow's report lock; refresh the actor, then lock the explicit permit."""
        try:
            principal = self._principal(user, binding)
            reference(authorization_ref, maximum=160)
            return self.read_permission(principal, authorization_ref, binding, operation)
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='recovery-permission/authorize')
