"""Current-user approval for isolated archival and separately opted-in source governance."""
from django.db import DatabaseError, connection

from data_security.contracts import (
    ContractViolation, Environment, Outlet, ProtectionContext, ProtectionError,
    Purpose, ReasonCode, Role,
)
from data_security.contracts.schema import reference, require
from users.models import CTFUser


class LegacyArchiveOwner:
    def __init__(self, *, capture, reconcile, identity, environment, domain, verify_content=None, govern=None):
        require(environment in (Environment.TEST, Environment.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
        self.capture, self.reconcile, self.identity = capture, reconcile, identity
        self.environment, self.domain = environment, domain
        self.verify_content, self.govern = verify_content, govern

    def run(self, *, user, operation, expected_count=None, expected_tail=None, archive_ref=None):
        """Trusted user comes from authentication, not the request body; no automatic grants."""
        trace = 'legacy-archive/approval'
        try:
            require(user.is_authenticated, ReasonCode.AUTHORIZATION_DENIED)
            actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
            require(actor is not None and actor.has_perm('audit.archive_auditledgerentry'),
                    ReasonCode.AUTHORIZATION_DENIED)
            require(connection.get_autocommit() and not connection.in_atomic_block,
                    ReasonCode.DELIVERY_UNKNOWN)
            require(operation in ('capture', 'reconcile', 'verify', 'quarantine', 'delete'), ReasonCode.INVALID_VALUE)
            if operation == 'delete':
                require(actor.has_perm('audit.delete_auditledgerentry') and
                        actor.has_perm('audit.delete_securityauditrecord'), ReasonCode.AUTHORIZATION_DENIED)
            if operation in ('quarantine', 'delete'):
                require(self.govern is not None, ReasonCode.SOURCE_NOT_APPROVED)
            if operation == 'verify':
                require(self.verify_content is not None, ReasonCode.KEY_UNAVAILABLE)
            if operation == 'capture':
                require(archive_ref is None, ReasonCode.INVALID_VALUE)
                trace = 'archive-approval/' + self.identity()
            else:
                require(expected_count is None and expected_tail is None, ReasonCode.INVALID_VALUE)
                reference(archive_ref)
                trace = archive_ref
            principal = ProtectionContext(schema_version=ProtectionContext.SCHEMA,
                actor_ref='user/' + str(actor.pk), authorization_ref=trace,
                scope_refs=('audit/legacy-v1',), environment=self.environment, domain=self.domain,
                outlet=Outlet.AUDIT, purpose=Purpose.SECURITY_AUDIT, role=Role(actor.role),
                object_ref='audit/legacy-v1', object_version='v1', source_ref=None,
                source_version=None, source_hash=None, trace_id=trace)
            if operation == 'capture':
                return self.capture(principal=principal, expected_count=expected_count, expected_tail=expected_tail)
            if operation == 'verify':
                return self.verify_content(principal=principal, archive_ref=archive_ref)
            if operation in ('quarantine', 'delete'):
                return self.govern(principal=principal, archive_ref=archive_ref, operation=operation)
            return self.reconcile(principal=principal, archive_ref=archive_ref)
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=trace)
