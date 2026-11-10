"""Prepare encrypted, unreadable uploads after the business owner admits them."""
import hashlib

from data_security.contracts import (
    BoundedPayload, ContractViolation, ObjectContext, PayloadKind, ProtectionError,
    ReasonCode, StoredObject,
)
from data_security.contracts.schema import require


class PrivateFilePreparation:
    def __init__(self, *, crypto, data_key, store, limits, operations=None):
        self.crypto, self.data_key, self.store, self.limits = crypto, data_key, store, limits
        self.operations = operations

    def prepare(self, payload: BoundedPayload, context: ObjectContext, *, operation=None) -> StoredObject | ProtectionError:
        # Business format checks and current upload permission belong to the owner.
        try:
            require(payload.kind is PayloadKind.BINARY, ReasonCode.INVALID_TYPE)
            require(payload.limits == self.limits, ReasonCode.LIMIT_EXCEEDED)
            if operation is not None:
                require(self.operations is not None, ReasonCode.SOURCE_NOT_APPROVED)
                input_hash = hashlib.sha256(payload.binary).hexdigest()
                retained = self.operations.retained(operation, context, input_hash)
                if retained is not None:
                    if not isinstance(retained, ProtectionError):
                        self.operations.confirm(operation, context, retained)
                    return retained
            envelope = self.crypto.seal(payload, context, self.data_key)
            if isinstance(envelope, ProtectionError):
                return envelope
            if operation is not None:
                self.operations.stage(operation, envelope, context, input_hash)
            candidate = self.store.write_candidate(envelope, context)
            if isinstance(candidate, ProtectionError):
                return candidate
            verified = self.store.verify(candidate, context)
            if operation is not None and not isinstance(verified, ProtectionError):
                self.operations.confirm(operation, context, verified)
            return verified
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id='private-file/prepare')
