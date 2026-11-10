"""Request-scoped risk adapter; the original risk service owns its records and locks."""
from datetime import datetime

from django.db import DatabaseError, IntegrityError, connection, transaction

from data_security.contracts import ContractViolation, ProtectionError, ReasonCode, content_hash
from data_security.contracts.schema import reference, require
from export_risk.contracts import (
    AuthorizationSnapshot, ExportRequestSnapshot, ExportRiskAssessment, NotExecutable, SourceMode,
)
from export_risk.decisions.service import (
    IdempotencyConflict, check_execution_eligibility, claim, consume, create_risk_decision,
    prepare_execution, recheck_delivered, recheck_execution,
)


class DjangoRiskPort:
    """Construct from a trusted owner's request/scope/policy, never download input.

    assess(request, policy) and authorize(request) supply the original risk DTOs.
    active_until(execution) is injected by B from the quota adapter. No service
    default or second reserve is available through this adapter. Claimed-execution
    recovery requires decide; delivered rechecks read the original admission instead.
    """
    def __init__(self, *, request, scope, domain_ref, policy_binding, environment,
                 assess, authorize, active_until, approval=None):
        require(environment in ('test', 'evaluation'), ReasonCode.SOURCE_NOT_APPROVED)
        require(type(request) is ExportRequestSnapshot, ReasonCode.INVALID_TYPE)
        require(request.environment == environment and
                request.source_mode in (SourceMode.SYNTHETIC, SourceMode.EVALUATION),
                ReasonCode.SOURCE_NOT_APPROVED)
        reference(domain_ref, maximum=120)
        self.request = request
        self.scope = scope
        self.domain_ref = domain_ref
        self.policy_binding = policy_binding
        self.environment = environment
        self.assess = assess
        self.authorize = authorize
        self.active_until = active_until
        self.approval = approval
        self._decision_id = None

    def decide(self, request, binding):
        """Return an eligible decision reference before the flow reserves its one hold."""
        self._decision_id = None
        try:
            require(request == self.request and binding == self.policy_binding,
                    ReasonCode.IDEMPOTENCY_CONFLICT)
            assessment = self.assess(request, binding)
            if isinstance(assessment, ProtectionError):
                return assessment
            require(type(assessment) is ExportRiskAssessment, ReasonCode.INVALID_TYPE)
            require((assessment.request_id, assessment.request_fingerprint, assessment.policy_version) ==
                    (request.request_id, request.request_fingerprint, binding.risk_version),
                    ReasonCode.IDEMPOTENCY_CONFLICT)
            require(assessment.input_source_mode in (SourceMode.SYNTHETIC, SourceMode.EVALUATION),
                    ReasonCode.SOURCE_NOT_APPROVED)
            key = 'ds-risk/' + content_hash({'request': vars(request), 'scope': self.scope,
                                           'domain': self.domain_ref, 'policy': binding})
            decision = create_risk_decision(assessment, request, idempotency_key=key)
            snapshot = self._current_authorization()
            if isinstance(snapshot, ProtectionError):
                return snapshot
            blocker = check_execution_eligibility(decision.decision_id, request, snapshot,
                                                  environment=self.environment, approval=self.approval)
            require(blocker is None, ReasonCode.AUTHORIZATION_DENIED)
            self._decision_id = decision.decision_id
            return decision.decision_id
        except ContractViolation as error:
            code = error.code
        except (IdempotencyConflict, IntegrityError):
            code = ReasonCode.IDEMPOTENCY_CONFLICT
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=self.request.request_id)

    def _current_authorization(self):
        snapshot = self.authorize(self.request)
        if isinstance(snapshot, ProtectionError):
            return snapshot
        require(type(snapshot) is AuthorizationSnapshot, ReasonCode.INVALID_TYPE)
        require(snapshot.data_domain == self.domain_ref, ReasonCode.AUTHORIZATION_DENIED)
        require(snapshot.source_mode in (SourceMode.SYNTHETIC, SourceMode.EVALUATION),
                ReasonCode.SOURCE_NOT_APPROVED)
        return snapshot

    def issue(self, execution):
        """Issue and claim once; logical-delivery replay belongs to ExportFlow."""
        return self._execution('issue', execution)

    def recheck(self, execution):
        return self._execution('recheck', execution)

    def recheck_delivered(self, execution):
        """Read current eligibility of the original consumed execution, without deciding again."""
        return self._execution('recheck_delivered', execution)

    def consume(self, execution):
        """Recheck and consume under the flow's outer UoW, never in autocommit."""
        return self._execution('consume', execution)

    def _execution(self, operation, execution):
        try:
            require(operation != 'consume' or connection.in_atomic_block,
                    ReasonCode.AUTHORIZATION_DENIED)
            if operation != 'recheck_delivered':
                require(self._decision_id is not None and execution.decision_id == self._decision_id,
                        ReasonCode.AUTHORIZATION_DENIED)
            require((execution.request_id, execution.request_fingerprint, execution.asset_version,
                     execution.subject_ref, execution.quantity, execution.environment, execution.scope,
                     execution.domain_ref, execution.policy_binding) ==
                    (self.request.request_id, self.request.request_fingerprint, self.request.asset_version,
                     self.request.subject_id, self.request.record_count, self.environment, self.scope,
                     self.domain_ref, self.policy_binding), ReasonCode.IDEMPOTENCY_CONFLICT)
            snapshot = self._current_authorization()
            if isinstance(snapshot, ProtectionError):
                return snapshot
            if operation == 'recheck_delivered':
                decision_key = 'ds-risk/' + content_hash({'request': vars(self.request), 'scope': self.scope,
                                                        'domain': self.domain_ref, 'policy': self.policy_binding})
                result = recheck_delivered(execution.authorization_id, self.request, snapshot,
                    decision_id=execution.decision_id, execution_id=execution.execution_id,
                    reservation_id=execution.reservation_id, decision_key=decision_key,
                    idempotency_key='ds-issue/' + execution.idempotency_key,
                    execution_binding_hash=content_hash(execution), expires_at=execution.expires_at,
                    environment=self.environment, approval=self.approval)
                require(result is True, ReasonCode.AUTHORIZATION_DENIED)
                return True

            def require_active(*, reservation_id, request_fingerprint, amount=None):
                require(reservation_id == execution.reservation_id and
                        request_fingerprint == execution.request_fingerprint and
                        (amount is None or amount == execution.quantity), ReasonCode.IDEMPOTENCY_CONFLICT)
                expiry = self.active_until(execution)
                if isinstance(expiry, ProtectionError):
                    raise ContractViolation(expiry.code)
                require(type(expiry) is datetime and expiry.utcoffset() is not None,
                        ReasonCode.AUTHORIZATION_DENIED)
                return min(expiry, execution.expires_at)

            with transaction.atomic():
                if operation == 'issue':
                    result = prepare_execution(execution.decision_id, self.request, snapshot,
                        idempotency_key='ds-issue/' + execution.idempotency_key, environment=self.environment,
                        approval=self.approval, reservation_id=execution.reservation_id,
                        authorization_id=execution.authorization_id, execution_id=execution.execution_id,
                        require_active=require_active, execution_binding_hash=content_hash(execution))
                    require(not isinstance(result, NotExecutable), ReasonCode.AUTHORIZATION_DENIED)
                    require(claim(execution.authorization_id, require_active=require_active),
                            ReasonCode.AUTHORIZATION_DENIED)
                # Re-read the claimed authorization after any deadline tightening.
                result = recheck_execution(execution.authorization_id, self.request, snapshot,
                    decision_id=execution.decision_id, execution_id=execution.execution_id,
                    reservation_id=execution.reservation_id, require_active=require_active,
                    environment=self.environment, approval=self.approval)
                require(not isinstance(result, NotExecutable), ReasonCode.AUTHORIZATION_DENIED)
                if operation == 'consume':
                    require(consume(execution.authorization_id), ReasonCode.AUTHORIZATION_DENIED)
                return result
        except ContractViolation as error:
            code = error.code
        except (IdempotencyConflict, IntegrityError):
            code = ReasonCode.IDEMPOTENCY_CONFLICT
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id=execution.execution_id)
