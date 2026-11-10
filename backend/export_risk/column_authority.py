"""Opt-in COLUMN_V1 risk authority; never a profile/history or production owner.

risk_inputs is bounded JSON with optional sensitivity_profile, feature_snapshot,
model_version and evaluation_time. {} means an actual-asset MISSING/unknown profile
and absent history. Retained feature claims are not an authoritative supplier:
no feature values enter judgment here, and history-dependent policies DEFER.

Load authenticates immutable grant/approval evidence outside a held-lock UoW.
Live authorize/status read only current users and the exact scoped row. status is
called under the original decision lock; authorize deliberately takes no row lock.
"""
from dataclasses import fields
import hashlib
import re
import uuid

from django.db import DatabaseError, IntegrityError, connection, transaction

from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, EventKind, FrozenJSON, Outcome,
    PolicyBinding, ProtectionError, ReasonCode, SecurityEventV2, TableScope, canonical_bytes, content_hash,
)
from data_security.contracts.schema import count, digest, reference, require, utc
from export_risk.contracts import (
    AuthorizationResult, AuthorizationSnapshot, Disposition, ExportRequestSnapshot,
    ExportRiskAssessment, FeatureSnapshot, NotExecutable, Obligation, QualityState,
    RecommendedAction, RiskLevel, SensitivityProfileRef, SourceMode,
)
from export_risk.contracts import reason_codes as rc
from export_risk.decisions.serde import _plain, obligations_to_json
from export_risk.decisions.service import IdempotencyConflict, check_execution_eligibility, create_risk_decision
from export_risk.judgment import assess_risk
from export_risk.judgment.validity import parse_aware_timestamp
from export_risk.models import ColumnRiskPermission, RiskDecision
from export_risk.policies.catalog import POLICIES, policy_hash, resolve_policy
from users.models import CTFUser

ADD = 'export_risk.add_columnriskpermission'
CHANGE = 'export_risk.change_columnriskpermission'
USE = 'export_risk.use_columnriskpermission'


def _document_hash(value):
    return hashlib.sha256(canonical_bytes(FrozenJSON(value), include_payload=True)).hexdigest()


def _request_wire(request):
    return {**vars(request), 'scope': list(request.scope), 'source_mode': request.source_mode.value}


def decode_request(value: FrozenJSON | dict) -> ExportRequestSnapshot:
    """Decode the complete original request; an empty fingerprint is pre-registration only."""
    value = FrozenJSON(value.to_value() if type(value) is FrozenJSON else value, max_bytes=16384).to_value()
    require(type(value) is dict and set(value) == {f.name for f in fields(ExportRequestSnapshot)},
            ReasonCode.INVALID_TYPE)
    for name, maximum in (('request_id', 160), ('revision', 40), ('subject_id', 160),
                          ('asset_version', 80), ('operation', 40), ('recipient_id', 160)):
        reference(value[name], maximum=maximum)
    require(re.fullmatch(r'user/[1-9][0-9]*', value['subject_id']) is not None,
            ReasonCode.AUTHORIZATION_DENIED)
    require(type(value['scope']) is list and 0 < len(value['scope']) <= 200 and
            all(type(item) is str for item in value['scope']) and
            len(set(value['scope'])) == len(value['scope']), ReasonCode.INVALID_VALUE)
    for item in value['scope']:
        reference(item)
    for name, maximum in (('purpose', 200), ('business_task_id', 160), ('trace_id', 160)):
        require(type(value[name]) is str and len(value[name]) <= maximum)
    count(value['record_count'], 2**53 - 1)
    require(value['environment'] in ('test', 'evaluation') and value['source_mode'] in
            (SourceMode.SYNTHETIC.value, SourceMode.EVALUATION.value), ReasonCode.SOURCE_NOT_APPROVED)
    require(value['schema_version'] == 'm0', ReasonCode.UNKNOWN_SCHEMA)
    if value['request_fingerprint'] != '':
        digest(value['request_fingerprint'])
    return ExportRequestSnapshot(**{**value, 'source_mode': SourceMode(value['source_mode'])})


def freeze_request(value: FrozenJSON | dict, *, request_id: str, subject_id: str,
                   asset_version: str, scope: tuple[str, ...], record_count: int,
                   environment: str, source_mode: SourceMode) -> FrozenJSON:
    """Freeze original fields with server-owned identity/count/provenance before fingerprinting."""
    value = FrozenJSON(value.to_value() if type(value) is FrozenJSON else value, max_bytes=16384).to_value()
    require(type(value) is dict and set(value) <= {f.name for f in fields(ExportRequestSnapshot)},
            ReasonCode.INVALID_TYPE)
    require(type(source_mode) is SourceMode, ReasonCode.INVALID_TYPE)
    defaults = dict(revision='1', operation='export', recipient_id='', purpose='', business_task_id='',
                    trace_id='', schema_version='m0')
    complete = {**defaults, **value, 'request_id': request_id, 'subject_id': subject_id,
                'asset_version': asset_version, 'scope': list(scope), 'record_count': record_count,
                'environment': environment, 'source_mode': source_mode.value, 'request_fingerprint': ''}
    return FrozenJSON(_request_wire(decode_request(complete)), max_bytes=16384)


def _binding(source_ref, source_hash, request, scope, domain_ref, policy_binding, risk_inputs):
    require(type(request) is ExportRequestSnapshot and type(scope) is TableScope and
            type(policy_binding) is PolicyBinding and type(risk_inputs) is FrozenJSON, ReasonCode.INVALID_TYPE)
    reference(source_ref)
    digest(source_hash)
    digest(request.request_fingerprint)
    reference(domain_ref, maximum=120)
    require(request.environment in ('test', 'evaluation') and request.source_mode in
            (SourceMode.SYNTHETIC, SourceMode.EVALUATION), ReasonCode.SOURCE_NOT_APPROVED)
    require(request.operation == 'export' and request.record_count > 0, ReasonCode.INVALID_VALUE)
    require(policy_binding.risk_version in POLICIES, ReasonCode.POLICY_NOT_APPROVED)
    require(policy_hash(resolve_policy(policy_binding.risk_version)) == policy_binding.risk_hash,
            ReasonCode.POLICY_NOT_APPROVED)
    risk_inputs = FrozenJSON(risk_inputs.to_value(), max_bytes=32768, max_nodes=1024, max_fields=256)
    return FrozenJSON(dict(source_ref=source_ref, source_hash=source_hash, request=_request_wire(request),
        scope=scope.to_wire(), domain_ref=domain_ref, policy_binding=policy_binding.to_wire(),
        risk_inputs=risk_inputs.to_value()))


def _inputs(risk_inputs, request, at):
    value = risk_inputs.to_value()
    require(type(value) is dict and set(value) <=
            {'sensitivity_profile', 'feature_snapshot', 'model_version', 'evaluation_time'}, ReasonCode.INVALID_TYPE)
    profile = value.get('sensitivity_profile')
    if profile is not None:
        require(type(profile) is dict and set(profile) <= {f.name for f in fields(SensitivityProfileRef)},
                ReasonCode.INVALID_TYPE)
        require(all(type(item) is str for key, item in profile.items() if key != 'categories') and
                type(profile.get('categories', [])) is list, ReasonCode.INVALID_TYPE)
        require(profile.get('asset_version', request.asset_version) == request.asset_version and
                profile.get('source_mode', request.source_mode.value) == request.source_mode.value,
                ReasonCode.SOURCE_NOT_APPROVED)
        require(profile.get('coverage', 'missing') == 'missing' and profile.get('status', 'unknown') == 'unknown' and
                profile.get('protection_level', 'unknown') == 'unknown' and profile.get('categories', []) == [] and
                not profile.get('profile_id', '') and not profile.get('detector_version', '') and
                not profile.get('level_policy_version', ''), ReasonCode.SOURCE_NOT_APPROVED)
    claim = value.get('feature_snapshot')
    if claim is not None:
        require(type(claim) is dict and set(claim) <= {f.name for f in fields(FeatureSnapshot)},
                ReasonCode.INVALID_TYPE)
        for name in ('feature_set_version', 'baseline_ref'):
            if name in claim:
                require(type(claim[name]) is str and len(claim[name]) <= 160)
        for name in ('as_of_time', 'data_watermark'):
            if name in claim:
                require(parse_aware_timestamp(claim[name]) is not None)
        for name in ('values', 'units'):
            require(type(claim.get(name, {})) is dict)
            for key, item in claim.get(name, {}).items():
                reference(key)
                require(type(item) in (int, float) if name == 'values' else type(item) is str)
        require(type(claim.get('missing', [])) is list)
        for item in claim.get('missing', []):
            reference(item)
        require(type(claim.get('current_request_counted', False)) is bool)
        require(type(claim.get('quality', 'missing')) is str and
                claim.get('quality', 'missing') in {q.value for q in QualityState})
        # A bounded retained claim is not observed history or an authenticated baseline.
    model = value.get('model_version', '')
    require(type(model) is str and len(model) <= 80)
    if model:
        reference(model, maximum=80)
    evaluated = value.get('evaluation_time', at.isoformat())
    require(parse_aware_timestamp(evaluated) is not None)
    return SensitivityProfileRef(profile_id='', asset_version=request.asset_version,
                                 source_mode=request.source_mode), model, evaluated


def _actor(user, capability):
    if not user.is_authenticated:
        return None
    actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
    return actor if actor is not None and actor.has_perm(capability) else None


def _requester(request):
    require(re.fullmatch(r'user/[1-9][0-9]*', request.subject_id) is not None, ReasonCode.AUTHORIZATION_DENIED)
    actor = CTFUser.objects.filter(pk=int(request.subject_id[5:]), is_active=True).first()
    require(actor is not None and actor.has_perm(USE), ReasonCode.AUTHORIZATION_DENIED)
    return actor


def _snapshot(permission_ref, request, domain_ref, policy_binding, observed_at, expires_at):
    return AuthorizationSnapshot(authority_source='export_risk.column-risk-authority.v1',
        snapshot_id=permission_ref, subject_id=request.subject_id, data_domain=domain_ref,
        result=AuthorizationResult.AUTHORIZED, allowed_scope=request.scope,
        allowed_operations=(request.operation,), allowed_recipients=(request.recipient_id,),
        policy_version=policy_binding.risk_version, observed_at=observed_at.isoformat(),
        valid_until=expires_at.isoformat(), environment=request.environment, source_mode=request.source_mode,
        evidence_refs=(permission_ref + '/grant',))


def _event(operation, permission_ref, request, policy_binding, actor_ref, at, document):
    return SecurityEventV2(schema_version=SecurityEventV2.SCHEMA, event_id=permission_ref + '/' + operation,
        kind=EventKind.AUTHORIZATION, actor_ref=actor_ref, object_ref=permission_ref, object_version='1',
        outcome=Outcome.SUCCEEDED, occurred_at=at, counts=(('processed', 1),), policy_binding=policy_binding,
        algorithm_versions=('column-risk-authority.v1', operation), key_versions=(),
        correlation_ref=request.request_id, reason=None, evidence_hashes=(('report', _document_hash(document)),))


def _error(error, trace):
    code = error.code if isinstance(error, ContractViolation) else (
        ReasonCode.IDEMPOTENCY_CONFLICT if isinstance(error, (IdempotencyConflict, IntegrityError))
        else ReasonCode.REPORT_MISMATCH if isinstance(error, (KeyError, TypeError, ValueError))
        else ReasonCode.DELIVERY_UNKNOWN)
    return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=trace)


class ColumnRiskOwner:
    def __init__(self, audit, read_event, clock, identity=None):
        self.audit, self.read_event, self.clock = audit, read_event, clock
        self.identity = identity or (lambda: uuid.uuid4().hex)

    def _record(self, event):
        receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
        if isinstance(receipt, ProtectionError):
            raise ContractViolation(receipt.code)
        require(type(receipt) is AuditReceipt and receipt.event_id == event.event_id and
                receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                ReasonCode.AUDIT_UNAVAILABLE)
        return receipt

    def _grant_document(self, row):
        document = FrozenJSON(row.grant_document).to_value()
        require(type(document) is dict and set(document) ==
                {'schema_version', 'permission_ref', 'binding', 'assessment', 'granted_by', 'granted_at',
                 'expires_at', 'decision_id', 'initial_disposition'}, ReasonCode.REPORT_MISMATCH)
        require(type(document['assessment']) is dict and set(document['assessment']) ==
                {f.name for f in fields(ExportRiskAssessment)}, ReasonCode.REPORT_MISMATCH)
        bound = document['binding']
        require(type(bound) is dict and set(bound) ==
                {'source_ref', 'source_hash', 'request', 'scope', 'domain_ref', 'policy_binding', 'risk_inputs'} and
                type(bound['request']) is dict and
                set(bound['request']) == {f.name for f in fields(ExportRequestSnapshot)}, ReasonCode.REPORT_MISMATCH)
        return document

    def _authenticate(self, row, request, policy_binding):
        require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
        document = self._grant_document(row)
        require(document['schema_version'] == 'export-risk.column-grant.v1' and
                document['permission_ref'] == row.permission_ref and document['decision_id'] == row.decision_id and
                document['expires_at'] == row.expires_at.isoformat() and
                _document_hash(document['binding']) == row.binding_hash and
                document['binding']['request']['request_fingerprint'] == row.request_fingerprint,
                ReasonCode.REPORT_MISMATCH)
        granted_at = parse_aware_timestamp(document['granted_at'])
        require(granted_at is not None, ReasonCode.REPORT_MISMATCH)
        event = _event('grant', row.permission_ref, request, policy_binding,
                       document['granted_by'], granted_at, document)
        require(row.grant_event_id == event.event_id, ReasonCode.REPORT_MISMATCH)
        actual = self.read_event(event.event_id)
        if isinstance(actual, ProtectionError):
            raise ContractViolation(actual.code)
        require(type(actual) is SecurityEventV2 and actual == event, ReasonCode.REPORT_MISMATCH)
        approved = row.approval_document
        if approved is not None:
            approved = FrozenJSON(approved).to_value()
            require(type(approved) is dict and set(approved) ==
                    {'schema_version', 'permission_ref', 'grant_hash', 'decision_id',
                     'request_fingerprint', 'approved_by', 'approved_at'}, ReasonCode.REPORT_MISMATCH)
            at = parse_aware_timestamp(approved['approved_at'])
            require(approved['schema_version'] == 'export-risk.column-approval.v1' and
                    approved['permission_ref'] == row.permission_ref and approved['grant_hash'] == _document_hash(document) and
                    approved['decision_id'] == row.decision_id and approved['request_fingerprint'] == request.request_fingerprint and
                    approved['approved_by'] != request.subject_id and at is not None and granted_at <= at < row.expires_at,
                    ReasonCode.REPORT_MISMATCH)
            event = _event('approve', row.permission_ref, request, policy_binding, approved['approved_by'], at, approved)
            require(row.approval_event_id == event.event_id, ReasonCode.REPORT_MISMATCH)
            actual = self.read_event(event.event_id)
            if isinstance(actual, ProtectionError):
                raise ContractViolation(actual.code)
            require(type(actual) is SecurityEventV2 and actual == event, ReasonCode.REPORT_MISMATCH)
        else:
            require(row.state != 'approved' and row.approval_event_id == '', ReasonCode.REPORT_MISMATCH)
        require(row.state in ('pending', 'approved', 'revoked'), ReasonCode.REPORT_MISMATCH)
        return document, approved

    def grant(self, user, source_ref, source_hash, request, scope, domain_ref, policy_binding, risk_inputs, expires_at):
        trace = 'column-risk/grant'
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            actor = _actor(user, ADD)
            require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
            bound = _binding(source_ref, source_hash, request, scope, domain_ref, policy_binding, risk_inputs)
            _requester(request)
            now = self.clock()
            utc(now)
            utc(expires_at)
            require(now < expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
            profile, model, evaluated = _inputs(risk_inputs, request, now)
            permission_ref = 'column-risk/' + self.identity()
            reference(permission_ref, maximum=48)
            snapshot = _snapshot(permission_ref, request, domain_ref, policy_binding, now, expires_at)
            assessment = assess_risk(request, profile, snapshot, None, model, policy_binding.risk_version, evaluated)
            key = 'ds-risk/' + content_hash({'request': vars(request), 'scope': scope,
                                            'domain': domain_ref, 'policy': policy_binding})
            with transaction.atomic():
                decision = create_risk_decision(assessment, request, idempotency_key=key)
                blocker = check_execution_eligibility(decision.decision_id, request, snapshot,
                                                      environment=request.environment)
                policy = resolve_policy(policy_binding.risk_version)
                if (blocker is None or blocker.disposition is Disposition.REQUIRE_APPROVAL) and (
                        policy.use_cumulative or policy.use_anomaly):
                    blocker = NotExecutable(Disposition.DEFER, (rc.DEGRADE_FEATURES_MISSING,))
                document = dict(schema_version='export-risk.column-grant.v1', permission_ref=permission_ref,
                    binding=bound.to_value(), assessment=_plain({**vars(assessment),
                        'recommended_action': assessment.recommended_action.value,
                        'risk_level': assessment.risk_level.value, 'input_quality': assessment.input_quality.value,
                        'input_source_mode': assessment.input_source_mode.value,
                        'obligations': obligations_to_json(assessment.obligations)}),
                    granted_by='user/' + str(actor.pk), granted_at=now.isoformat(),
                    expires_at=expires_at.isoformat(), decision_id=decision.decision_id,
                    initial_disposition=blocker.disposition.value if blocker else '')
                row = ColumnRiskPermission.objects.create(permission_ref=permission_ref, decision=decision,
                    request_fingerprint=request.request_fingerprint, binding_hash=_document_hash(bound.to_value()),
                    grant_document=document, grant_event_id=permission_ref + '/grant', expires_at=expires_at,
                    state='pending')
                receipt = self._record(_event('grant', permission_ref, request, policy_binding,
                                              document['granted_by'], now, document))
            return row.permission_ref, receipt
        except (ContractViolation, IdempotencyConflict, DatabaseError) as error:
            return _error(error, trace)

    def load(self, user, permission_ref, source_ref, source_hash, request, scope, domain_ref, policy_binding, risk_inputs):
        try:
            reference(permission_ref)
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            actor = _actor(user, USE)
            require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
            bound = _binding(source_ref, source_hash, request, scope, domain_ref, policy_binding, risk_inputs)
            require(request.subject_id == 'user/' + str(actor.pk), ReasonCode.AUTHORIZATION_DENIED)
            row = ColumnRiskPermission.objects.filter(permission_ref=permission_ref).first()
            require(row is not None and row.binding_hash == _document_hash(bound.to_value()), ReasonCode.AUTHORIZATION_DENIED)
            document, approved = self._authenticate(row, request, policy_binding)
            require(FrozenJSON(document['binding']) == bound, ReasonCode.AUTHORIZATION_DENIED)
            profile, _, _ = _inputs(risk_inputs, request, parse_aware_timestamp(document['granted_at']))
            decision = RiskDecision.objects.filter(decision_id=row.decision_id).first()
            require(decision is not None, ReasonCode.AUTHORIZATION_DENIED)
            value = document['assessment']
            require(value['schema_version'] == 'm0' and type(value['obligations']) is list,
                    ReasonCode.REPORT_MISMATCH)
            assessment = ExportRiskAssessment(**{**value,
                'recommended_action': RecommendedAction(value['recommended_action']),
                'risk_level': RiskLevel(value['risk_level']), 'input_quality': QualityState(value['input_quality']),
                'input_source_mode': SourceMode(value['input_source_mode']),
                'obligations': tuple(Obligation(**obligation) for obligation in value['obligations'])})
            supplier = ColumnRiskSupplier(self, user, row, document, approved, request, scope, domain_ref,
                                          policy_binding, profile, decision.valid_until, assessment)
            supplier._match_decision(decision, assessment)
            return supplier
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return _error(error, 'column-risk/load')

    def approve(self, user, permission_ref, decision_id=None):
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            actor = _actor(user, CHANGE)
            require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
            reference(permission_ref)
            row = ColumnRiskPermission.objects.filter(permission_ref=permission_ref).first()
            require(row is not None, ReasonCode.AUTHORIZATION_DENIED)
            bound = self._grant_document(row)['binding']
            request = decode_request(bound['request'])
            scope = TableScope.from_wire(bound['scope'])
            policy = PolicyBinding.from_wire(bound['policy_binding'])
            requester = _requester(request)
            require(actor.pk != requester.pk and (decision_id is None or decision_id == row.decision_id),
                    ReasonCode.AUTHORIZATION_DENIED)
            supplier = self.load(requester, permission_ref, bound['source_ref'], bound['source_hash'], request,
                                 scope, bound['domain_ref'], policy, FrozenJSON(bound['risk_inputs']))
            if isinstance(supplier, ProtectionError):
                return supplier
            require(supplier._history_blocker() is None, ReasonCode.AUTHORIZATION_DENIED)
            with transaction.atomic():
                decision = RiskDecision.objects.select_for_update().get(decision_id=supplier.decision_id)
                current = ColumnRiskPermission.objects.select_for_update().get(permission_ref=permission_ref)
                supplier._live(current)
                require(current.state == 'pending' and current.approval_document is None,
                        ReasonCode.AUTHORIZATION_DENIED)
                now = self.clock()
                require(now < supplier.active_until, ReasonCode.AUTHORIZATION_EXPIRED)
                _requester(request)
                actor = _actor(user, CHANGE)
                require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
                snapshot = _snapshot(permission_ref, request, bound['domain_ref'], policy, now, current.expires_at)
                blocker = check_execution_eligibility(decision.decision_id, request, snapshot,
                                                      environment=request.environment)
                require(blocker is not None and blocker.disposition is Disposition.REQUIRE_APPROVAL,
                        ReasonCode.AUTHORIZATION_DENIED)
                supplier._match_decision(decision, supplier._assessment_value)
                approved = dict(schema_version='export-risk.column-approval.v1', permission_ref=permission_ref,
                    grant_hash=_document_hash(current.grant_document), decision_id=decision.decision_id,
                    request_fingerprint=request.request_fingerprint, approved_by='user/' + str(actor.pk),
                    approved_at=now.isoformat())
                current.state, current.approval_document = 'approved', approved
                current.approval_event_id = permission_ref + '/approve'
                current.save(update_fields=['state', 'approval_document', 'approval_event_id'])
                return self._record(_event('approve', permission_ref, request, policy, approved['approved_by'], now, approved))
        except (ContractViolation, DatabaseError) as error:
            return _error(error, 'column-risk/approve')

    def revoke(self, user, permission_ref):
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            actor = _actor(user, CHANGE)
            require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
            reference(permission_ref)
            row = ColumnRiskPermission.objects.filter(permission_ref=permission_ref).first()
            require(row is not None, ReasonCode.AUTHORIZATION_DENIED)
            bound = self._grant_document(row)['binding']
            request = decode_request(bound['request'])
            policy = PolicyBinding.from_wire(bound['policy_binding'])
            document, approved = self._authenticate(row, request, policy)
            with transaction.atomic():
                # Management uses decision -> permission, matching the status callback.
                RiskDecision.objects.select_for_update().get(decision_id=row.decision_id)
                current = ColumnRiskPermission.objects.select_for_update().get(permission_ref=permission_ref)
                require(FrozenJSON(current.grant_document) == FrozenJSON(document) and
                        FrozenJSON(current.approval_document) == FrozenJSON(approved) and
                        current.state != 'revoked', ReasonCode.AUTHORIZATION_DENIED)
                current.state, current.revoked_at = 'revoked', self.clock()
                current.save(update_fields=['state', 'revoked_at'])
                revoked = dict(grant_hash=_document_hash(document), approval_hash=_document_hash(approved),
                               revoked_at=current.revoked_at.isoformat(), decision_id=current.decision_id)
                return self._record(_event('revoke', permission_ref, request, policy,
                                           'user/' + str(actor.pk), current.revoked_at, revoked))
        except (ContractViolation, DatabaseError) as error:
            return _error(error, 'column-risk/revoke')


class ColumnRiskSupplier:
    is_production_authority = False

    def __init__(self, owner, user, row, document, approved, request, scope, domain_ref,
                 policy_binding, profile, decision_until, assessment):
        self.owner, self.user, self.request, self.scope = owner, user, request, scope
        self.domain_ref, self.policy_binding = domain_ref, policy_binding
        self._policy = resolve_policy(policy_binding.risk_version)
        self.permission_ref, self.decision_id = row.permission_ref, row.decision_id
        self._document, self._approved = FrozenJSON(document), FrozenJSON(approved) if approved is not None else None
        self._profile, self._assessment_value = profile, assessment
        self._binding_hash, self._expires_at = row.binding_hash, row.expires_at
        self.active_until = min(row.expires_at, decision_until)
        self.approval = self

    def _live(self, row):
        require(row is not None and row.decision_id == self.decision_id and
                row.request_fingerprint == self.request.request_fingerprint and
                row.binding_hash == self._binding_hash and FrozenJSON(row.grant_document) == self._document and
                row.grant_event_id == self.permission_ref + '/grant' and
                row.expires_at == self._expires_at, ReasonCode.AUTHORIZATION_DENIED)

    def _match_decision(self, decision, assessment):
        require((assessment.request_id, assessment.request_fingerprint, assessment.policy_version,
                 assessment.authorization_snapshot_id) ==
                (self.request.request_id, self.request.request_fingerprint, self.policy_binding.risk_version,
                 self.permission_ref), ReasonCode.AUTHORIZATION_DENIED)
        require((decision.request_id, decision.request_fingerprint, decision.asset_version, decision.environment,
                 decision.source_mode, decision.profile_id, decision.scope, decision.policy_version,
                 decision.model_version, decision.feature_set_version, decision.action, decision.obligations) ==
                (self.request.request_id, self.request.request_fingerprint, self.request.asset_version,
                 self.request.environment, assessment.input_source_mode.value, assessment.profile_id,
                 list(self.request.scope), self.policy_binding.risk_version, assessment.model_version,
                 assessment.feature_set_version, assessment.recommended_action.value,
                 obligations_to_json(assessment.obligations)), ReasonCode.AUTHORIZATION_DENIED)

    def _history_blocker(self):
        if self._policy.use_cumulative or self._policy.use_anomaly:
            return NotExecutable(Disposition.DEFER, (rc.DEGRADE_FEATURES_MISSING,))
        return None

    def assess(self, request, policy_binding):
        try:
            require(request == self.request and policy_binding == self.policy_binding, ReasonCode.IDEMPOTENCY_CONFLICT)
            require(self._history_blocker() is None, ReasonCode.AUTHORIZATION_DENIED)
            return self._assessment_value
        except ContractViolation as error:
            return _error(error, 'column-risk/assess')

    def authorize(self, request):
        try:
            require(request == self.request, ReasonCode.IDEMPOTENCY_CONFLICT)
            # No select_for_update here: the original decision is not locked yet.
            row = ColumnRiskPermission.objects.filter(permission_ref=self.permission_ref).first()
            self._live(row)
            actor = _actor(self.user, USE)
            require(actor is not None and self.request.subject_id == 'user/' + str(actor.pk) and
                    row.state != 'revoked' and row.revoked_at is None, ReasonCode.AUTHORIZATION_DENIED)
            now = self.owner.clock()
            require(now < self.active_until, ReasonCode.AUTHORIZATION_EXPIRED)
            return _snapshot(self.permission_ref, request, self.domain_ref, self.policy_binding, now, row.expires_at)
        except (ContractViolation, DatabaseError) as error:
            return _error(error, 'column-risk/authorize')

    def status(self, decision_id, request_fingerprint):
        if (decision_id, request_fingerprint) != (self.decision_id, self.request.request_fingerprint):
            return 'none'
        with transaction.atomic():
            row = ColumnRiskPermission.objects.select_for_update().filter(permission_ref=self.permission_ref).first()
            if row is None:
                return 'none'
            self._live(row)
            if row.state == 'revoked' or row.revoked_at is not None:
                return 'revoked'
            actor = _actor(self.user, USE)
            if actor is None or self.request.subject_id != 'user/' + str(actor.pk) or self.owner.clock() >= self.active_until:
                return 'none'
            if row.state == 'pending':
                return 'pending'
            require(row.state == 'approved' and self._approved is not None and
                    FrozenJSON(row.approval_document) == self._approved and
                    row.approval_event_id == self.permission_ref + '/approve', ReasonCode.AUTHORIZATION_DENIED)
            require(self._history_blocker() is None, ReasonCode.AUTHORIZATION_DENIED)
            return 'approved'

    def admit(self):
        """Return the genuine assessment, persisted decision id and original/non-executable blocker.

        Owner grant expiry/withdrawal is translated to the matching original DEFER/
        DENY blocker. A required-history blocker never overwrites a hard DENY/DEFER.
        No reservation, execution authorization, claim or original input read occurs.
        """
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            assessment = self._assessment_value
            key = 'ds-risk/' + content_hash({'request': vars(self.request), 'scope': self.scope,
                                            'domain': self.domain_ref, 'policy': self.policy_binding})
            decision = create_risk_decision(assessment, self.request, idempotency_key=key)
            require(decision.decision_id == self.decision_id, ReasonCode.IDEMPOTENCY_CONFLICT)
            self._match_decision(decision, assessment)
            snapshot = self.authorize(self.request)
            if isinstance(snapshot, ProtectionError):
                if snapshot.code is ReasonCode.AUTHORIZATION_EXPIRED:
                    blocker = NotExecutable(Disposition.DEFER, (rc.EXEC_AUTHORIZATION_EXPIRED,))
                elif snapshot.code is ReasonCode.AUTHORIZATION_DENIED:
                    blocker = NotExecutable(Disposition.DENY, (rc.EXEC_AUTHORIZATION_FORBIDDEN,))
                else:
                    return snapshot
            else:
                blocker = check_execution_eligibility(decision.decision_id, self.request, snapshot,
                    environment=self.request.environment, approval=self.approval)
                if blocker is None or blocker.disposition is Disposition.REQUIRE_APPROVAL:
                    blocker = self._history_blocker() or blocker
            return assessment, decision.decision_id, blocker
        except (ContractViolation, IdempotencyConflict, DatabaseError) as error:
            return _error(error, 'column-risk/admit')
