"""PostgreSQL policy storage. Database failure never selects a file policy."""
from django.db import DatabaseError, connection, transaction

from data_security.contracts import ContractViolation, PolicySnapshot, ProtectionError, ReasonCode
from data_security.contracts.schema import require
from data_security.adapters.persistence.models import PolicyVersion
from data_security.adapters.persistence.policy_writes import check_write


class ORMPolicyRepository:
    def __init__(self, *, writable=False):
        self.writable = writable

    def read(self, binding):
        try:
            document = PolicyVersion.objects.filter(version=binding.protection_version).values_list('document', flat=True).first()
            require(document is not None, ReasonCode.POLICY_NOT_APPROVED)
            snapshot = PolicySnapshot.from_wire(document)
            require((snapshot.version, snapshot.content_hash) ==
                    (binding.protection_version, binding.protection_hash), ReasonCode.POLICY_NOT_APPROVED)
            return snapshot
        except (DatabaseError, ContractViolation):
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.POLICY_NOT_APPROVED, retryable=False, trace_id='policy/orm')

    def put(self, snapshot, expected_version):
        if not self.writable:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.AUTHORIZATION_DENIED, retryable=False, trace_id='policy/orm')
        try:
            with transaction.atomic():
                # Serialize CAS including creation of the very first version.
                require(connection.vendor == 'postgresql', ReasonCode.POLICY_NOT_APPROVED)
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', (0x44535034, 1))
                snapshots = [PolicySnapshot.from_wire(document) for document in
                    PolicyVersion.objects.order_by('id').values_list('document', flat=True)]
                check_write(snapshots, snapshot, expected_version)
                PolicyVersion.objects.update_or_create(version=snapshot.version,
                    defaults={'document': snapshot.to_wire()})
            return True
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=error.code, retryable=False, trace_id='policy/orm')
        except DatabaseError:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.POLICY_NOT_APPROVED, retryable=False, trace_id='policy/orm')
