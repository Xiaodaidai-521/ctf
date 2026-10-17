class ControlledExportError(Exception):
    code = "CONTROLLED_EXPORT_ERROR"

    def __init__(self, message=None, *, code=None):
        super().__init__(message or self.code)
        self.code = code or self.code


class ContractError(ControlledExportError):
    code = "CONTRACT_INVALID"


class AuthorizationRejected(ControlledExportError):
    code = "AUTHORIZATION_REJECTED"


class IdempotencyConflict(ControlledExportError):
    code = "IDEMPOTENCY_CONFLICT"


class ExecutionConflict(ControlledExportError):
    code = "EXECUTION_CONFLICT"


class UnsupportedContent(ControlledExportError):
    code = "UNSUPPORTED_CONTENT"


class ShareAccessDenied(ControlledExportError):
    code = "SHARE_ACCESS_DENIED"


class ArtifactIntegrityError(ControlledExportError):
    code = "ARTIFACT_INTEGRITY_FAILED"
