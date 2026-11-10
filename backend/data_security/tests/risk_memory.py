"""Single-threaded RiskPort model; no ORM, locks, persistence or UoW rollback."""
from dataclasses import replace
from datetime import datetime, timedelta

from data_security.contracts import ContractViolation, ProtectionError, ReasonCode, content_hash
from data_security.contracts.schema import reference, require
from export_risk.contracts import (
    AuthorizationResult, AuthorizationSnapshot, ExecutionAuthorization, ExportRequestSnapshot,
    ExportRiskAssessment, RecommendedAction, SourceMode,
)
from export_risk.judgment.hard_constraints import evaluate_hard_constraints
from export_risk.judgment.validity import authorization_validity, parse_aware_timestamp


class MemoryRiskPort:
    def __init__(self, *, decisions, authorizations, issue_keys, events, clock, in_work,
                 request, scope, domain_ref, policy_binding, environment,
                 assess, authorize, active_until, approval=None):
        require(environment in ('test', 'evaluation'), ReasonCode.SOURCE_NOT_APPROVED)
        require(type(request) is ExportRequestSnapshot, ReasonCode.INVALID_TYPE)
        require(request.environment == environment and
                request.source_mode in (SourceMode.SYNTHETIC, SourceMode.EVALUATION),
                ReasonCode.SOURCE_NOT_APPROVED)
        reference(domain_ref, maximum=120)
        self.decisions, self.authorizations = decisions, authorizations
        self.issue_keys, self.events, self.clock, self.in_work = issue_keys, events, clock, in_work
        self.request, self.scope, self.domain_ref = request, scope, domain_ref
        self.policy_binding, self.environment = policy_binding, environment
        self.assess, self.authorize, self.active_until, self.approval = assess, authorize, active_until, approval
        self._decision_id = None

    def _eligible(self, decision):
        snapshot = self.authorize(self.request)
        if isinstance(snapshot, ProtectionError):
            return snapshot
        require(type(snapshot) is AuthorizationSnapshot, ReasonCode.INVALID_TYPE)
        require(snapshot.data_domain == self.domain_ref, ReasonCode.AUTHORIZATION_DENIED)
        require(snapshot.source_mode in (SourceMode.SYNTHETIC, SourceMode.EVALUATION),
                ReasonCode.SOURCE_NOT_APPROVED)
        require(decision['status'] == 'valid' and self.clock() < decision['expires_at'],
                ReasonCode.AUTHORIZATION_DENIED)
        require(snapshot.environment == self.environment and snapshot.result is AuthorizationResult.AUTHORIZED
                and not evaluate_hard_constraints(self.request, snapshot).triggered
                and authorization_validity(snapshot, self.clock().isoformat()) is None,
                ReasonCode.AUTHORIZATION_DENIED)
        assessment = decision['assessment']
        require(assessment.recommended_action not in (RecommendedAction.DENY, RecommendedAction.DEFER),
                ReasonCode.AUTHORIZATION_DENIED)
        if assessment.recommended_action is RecommendedAction.REQUIRE_APPROVAL:
            require(self.approval is not None and
                    self.approval.status(decision['id'], self.request.request_fingerprint) == 'approved',
                    ReasonCode.AUTHORIZATION_DENIED)
        require(all(o.type in ('mask', 'approval') for o in assessment.obligations),
                ReasonCode.AUTHORIZATION_DENIED)
        return snapshot

    def decide(self, request, binding):
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
            key = content_hash({'request': vars(request), 'scope': self.scope,
                                'domain': self.domain_ref, 'policy': binding})
            decision = self.decisions.get(key)
            if decision is None:
                decision = dict(id='memory-decision/' + key, assessment=assessment,
                                expires_at=self.clock() + timedelta(seconds=600), status='valid')
                self.decisions[key] = decision
                self.events.append('decision.issued')
            else:
                original = decision['assessment']
                require((assessment.recommended_action, assessment.obligations, assessment.policy_version) ==
                        (original.recommended_action, original.obligations, original.policy_version),
                        ReasonCode.IDEMPOTENCY_CONFLICT)
            snapshot = self._eligible(decision)
            if isinstance(snapshot, ProtectionError):
                return snapshot
            self._decision_id = decision['id']
            return self._decision_id
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=self.request.request_id)

    def issue(self, execution):
        return self._execution('issue', execution)

    def recheck(self, execution):
        return self._execution('recheck', execution)

    def recheck_delivered(self, execution):
        return self._execution('recheck_delivered', execution)

    def consume(self, execution):
        return self._execution('consume', execution)

    def _execution(self, operation, execution):
        try:
            require(operation != 'consume' or self.in_work(), ReasonCode.AUTHORIZATION_DENIED)
            if operation != 'recheck_delivered':
                require(self._decision_id is not None and execution.decision_id == self._decision_id,
                        ReasonCode.AUTHORIZATION_DENIED)
            require((execution.request_id, execution.request_fingerprint, execution.asset_version,
                     execution.subject_ref, execution.quantity, execution.environment, execution.scope,
                     execution.domain_ref, execution.policy_binding) ==
                    (self.request.request_id, self.request.request_fingerprint, self.request.asset_version,
                     self.request.subject_id, self.request.record_count, self.environment, self.scope,
                     self.domain_ref, self.policy_binding), ReasonCode.IDEMPOTENCY_CONFLICT)
            if operation == 'recheck_delivered':
                key = content_hash({'request': vars(self.request), 'scope': self.scope,
                                    'domain': self.domain_ref, 'policy': self.policy_binding})
                decision = self.decisions.get(key)
                require(decision is not None and decision['id'] == execution.decision_id,
                        ReasonCode.AUTHORIZATION_DENIED)
            else:
                decision = next(d for d in self.decisions.values() if d['id'] == self._decision_id)
            snapshot = self._eligible(decision)
            if isinstance(snapshot, ProtectionError):
                return snapshot
            auth = self.authorizations.get(execution.authorization_id)
            identity = (execution.decision_id, execution.reservation_id,
                        execution.authorization_id, execution.execution_id)
            if operation == 'recheck_delivered':
                require(auth is not None and auth['state'] == 'consumed' and auth['identity'] == identity,
                        ReasonCode.AUTHORIZATION_DENIED)
                previous = self.issue_keys.get(execution.idempotency_key)
                require(previous is not None, ReasonCode.AUTHORIZATION_DENIED)
                require(previous == identity and auth['binding'] == execution, ReasonCode.IDEMPOTENCY_CONFLICT)
                expiry = parse_aware_timestamp(auth['dto'].valid_until)
                require(expiry is not None and self.clock() < min(expiry, execution.expires_at,
                        decision['expires_at'], parse_aware_timestamp(snapshot.valid_until)),
                        ReasonCode.AUTHORIZATION_DENIED)
                return True
            if operation == 'issue':
                previous = self.issue_keys.get(execution.idempotency_key)
                require(previous is None or previous == identity, ReasonCode.IDEMPOTENCY_CONFLICT)
                require(auth is None, ReasonCode.AUTHORIZATION_DENIED)
            else:
                require(auth is not None and auth['state'] == 'claiming' and
                        auth['identity'] == identity, ReasonCode.AUTHORIZATION_DENIED)
                require(self.clock() < datetime.fromisoformat(auth['dto'].valid_until),
                        ReasonCode.AUTHORIZATION_DENIED)
            expiry = self.active_until(execution)
            if isinstance(expiry, ProtectionError):
                raise ContractViolation(expiry.code)
            require(type(expiry) is datetime and expiry.utcoffset() is not None,
                    ReasonCode.AUTHORIZATION_DENIED)
            expiry = min(expiry, execution.expires_at, decision['expires_at'],
                         parse_aware_timestamp(snapshot.valid_until))
            if auth is not None:
                expiry = min(expiry, datetime.fromisoformat(auth['dto'].valid_until))
            require(self.clock() < expiry, ReasonCode.AUTHORIZATION_DENIED)
            if operation == 'issue':
                assessment = decision['assessment']
                dto = ExecutionAuthorization(authorization_id=execution.authorization_id,
                    execution_id=execution.execution_id, decision_id=execution.decision_id,
                    request_fingerprint=self.request.request_fingerprint,
                    asset_version=self.request.asset_version, profile_id=assessment.profile_id,
                    scope=self.request.scope, obligations=assessment.obligations,
                    reservation_id=execution.reservation_id, valid_until=expiry.isoformat())
                self.authorizations[execution.authorization_id] = dict(
                    dto=dto, identity=identity, state='claiming', binding=execution)
                self.issue_keys[execution.idempotency_key] = identity
                self.events.append('execution.authorized')
                return dto
            auth['dto'] = replace(auth['dto'], valid_until=expiry.isoformat())
            if operation == 'consume':
                auth['state'] = 'consumed'
            return auth['dto']
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id=execution.execution_id)
