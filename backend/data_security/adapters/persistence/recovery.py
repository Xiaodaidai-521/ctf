"""Current recovery permission, read under the flow's report -> permission lock order."""
from dataclasses import replace

from django.db import DatabaseError, connection, transaction

from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, Environment, EventKind, Outcome, Outlet,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, SecurityEventV2, content_hash,
)
from data_security.contracts.schema import reference, require

from .models import RecoveryPermission


class DjangoRecoveryPermissionWriter:
    """Persist an owner-authorized grant/revocation and its v2 event in one short UoW."""
    def __init__(self, *, record_event, policy_binding, clock):
        self.record_event, self.policy_binding, self.clock = record_event, policy_binding, clock

    def write(self, *, operation, binding, principal, authorization_ref, event_id, grant):
        try:
            with transaction.atomic():
                if operation == 'grant':
                    permission = RecoveryPermission.objects.create(authorization_ref=authorization_ref,
                        binding_hash=content_hash(binding), **grant)
                else:
                    permission = RecoveryPermission.objects.select_for_update().filter(
                        authorization_ref=authorization_ref).first()
                    require(permission is not None and permission.binding_hash == content_hash(binding),
                            ReasonCode.AUTHORIZATION_DENIED)
                    if permission.revoked_at is None:
                        permission.revoked_at = self.clock()
                        permission.save(update_fields=['revoked_at'])
                metadata = {name: getattr(permission, name) for name in (
                    'authorization_ref', 'actor_ref', 'binding_hash', 'allow_release',
                    'allow_reconcile', 'expires_at', 'revoked_at')}
                event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
                    event_id=event_id, kind=EventKind.AUTHORIZATION, actor_ref=principal.actor_ref,
                    object_ref=authorization_ref, object_version='1', outcome=Outcome.SUCCEEDED,
                    occurred_at=self.clock(), counts=(('processed', 1),),
                    policy_binding=self.policy_binding, algorithm_versions=('recovery-permission.v1', operation),
                    key_versions=(), correlation_ref=binding.execution_id, reason=None,
                    evidence_hashes=(('report', content_hash(metadata)),))
                receipt = self.record_event(event, Durability.LEDGER_CONFIRMED)
                if isinstance(receipt, ProtectionError):
                    require(False, receipt.code)
                require(type(receipt) is AuditReceipt and receipt.event_id == event_id and
                        receipt.durability is Durability.LEDGER_CONFIRMED and
                        receipt.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
            return receipt
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=authorization_ref)


class DjangoRecoveryAuthorization:
    """B supplies the authenticated principal and an explicit owner-issued permission.

    This adapter neither authenticates client input nor issues permissions. No role,
    previous export authorization, or absent permission grants recovery by default.
    """
    def __init__(self, *, principal, authorization_ref, clock):
        require(type(principal) is ProtectionContext, ReasonCode.INVALID_TYPE)
        require(principal.environment in (Environment.TEST, Environment.EVALUATION),
                ReasonCode.SOURCE_NOT_APPROVED)
        reference(authorization_ref, maximum=160)
        self.principal = principal
        self.authorization_ref = authorization_ref
        self.clock = clock

    def __call__(self, binding, operation):
        try:
            require(connection.in_atomic_block and operation in ('release', 'reconcile'),
                    ReasonCode.AUTHORIZATION_DENIED)
            require((binding.environment, binding.domain_ref) ==
                    (self.principal.environment.value, self.principal.domain), ReasonCode.AUTHORIZATION_DENIED)
            permission = RecoveryPermission.objects.select_for_update().get(authorization_ref=self.authorization_ref)
            require(permission.actor_ref == self.principal.actor_ref and
                    permission.binding_hash == content_hash(binding) and permission.revoked_at is None and
                    (permission.allow_release if operation == 'release' else permission.allow_reconcile),
                    ReasonCode.AUTHORIZATION_DENIED)
            # Evaluate the current deadline after any report or permission lock wait.
            require(self.clock() < permission.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
            return replace(self.principal, authorization_ref=permission.authorization_ref,
                scope_refs=(binding.reservation_id,), outlet=Outlet.AUDIT, purpose=Purpose.SECURITY_AUDIT,
                object_ref=binding.execution_id, object_version=binding.asset_version,
                source_ref=None, source_version=None, source_hash=None)
        except ContractViolation as error:
            code = error.code
        except RecoveryPermission.DoesNotExist:
            code = ReasonCode.AUTHORIZATION_DENIED
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=binding.execution_id)
