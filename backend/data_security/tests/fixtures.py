from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone

from data_security.contracts import *

AT = datetime(2026, 11, 4, tzinfo=timezone.utc)
HASH = content_hash({'fixture': 'metadata-only'})


def dto(cls, **values):
    return cls(schema_version=cls.SCHEMA, **values)


def approval(value, *, subject='actor/requester', at=AT):
    return dto(Approval, approval_ref='approval/fixture', requested_by=subject,
               approved_by='actor/reviewer', approved_at=at, content_hash=value)


def examples():
    objects = {Limits: BASELINE_LIMITS}
    context = dto(ProtectionContext, actor_ref='actor/requester', authorization_ref='authorization/fixture',
        scope_refs=('scope/fixture',), environment=Environment.TEST, domain='domain/test',
        outlet=Outlet.EXPORT, purpose=Purpose.DELIVERY, role=Role.SERVICE, object_ref='object/fixture',
        object_version='v1', source_ref=None, source_version=None, source_hash=None, trace_id='trace/fixture')
    payload = dto(BoundedPayload, kind=PayloadKind.TEXT, media_type=MediaType.TEXT, text='fixture body',
                  tree=None, binary=None, limits=BASELINE_LIMITS)
    coverage = dto(Coverage, unit=Unit.CELL, total=1, eligible=1, processed=1, excluded=0,
                   failed=0, unknown=0, unscanned=0, version='coverage-v1')
    location = dto(Location, kind=LocationKind.CELL_SPAN, sheet_id='csv:0', source_row=2,
                   column_id='column:1', start=0, end=2, json_path=())
    finding = dto(Finding, category=Category.EMAIL, level=Level.L2, rule_version='email-v1',
                  location=location, reason=ReasonCode.MATCHED_FORMAT)
    column = dto(TableColumn, sheet_id='csv:0', column_id='column:1', source_index=1, label='contact')
    cell = dto(TableCell, sheet_id='csv:0', column_id='column:1', source_row=2, logical_record=2,
               original_text='Ａ🙂x', normalized_text='A🙂x', source_spans=((0, 1), (1, 2), (2, 3)),
               mapping_proven=True)
    snapshot = dto(TableSnapshot, asset_version='asset/v1', input_hash=HASH, media_type=MediaType.CSV,
        sheet_ids=('csv:0',), columns=(column,), cells=(cell,), coverage=coverage,
        limits=BASELINE_LIMITS, coordinate_version='source-codepoint-half-open.v1')
    algorithm = dto(AlgorithmSpec, algorithm=Algorithm.REPLACE, version='v1', replacement=Replacement.EMAIL,
        keep_prefix=None, keep_suffix=None, mask_symbol=None, max_length=None, ipv4_prefix=None,
        pseudonym_bits=None, key_ref=None)
    teaching_fields = dict(schema_version=TeachingException.SCHEMA, source_ref='fixture/published',
        source_version='v1', source_hash=HASH, field_refs=('content/endpoint',), category=Category.IPV4,
        outlet=Outlet.API, purpose=Purpose.TEACHING, expires_at=AT + timedelta(hours=1))
    teaching = TeachingException(**teaching_fields, approval=approval(content_hash(teaching_fields)))
    rule = dto(PolicyRule, category=Category.EMAIL, outlet=Outlet.EXPORT, role=Role.SERVICE,
               purpose=Purpose.DELIVERY, action=algorithm)
    policy_fields = dict(schema_version=PolicySnapshot.SCHEMA, version='fixture-v1', rules=(rule,),
        teaching_exceptions=(teaching,), effective_at=AT, expires_at=AT + timedelta(hours=1))
    policy_hash = content_hash(policy_fields)
    policy = PolicySnapshot(**policy_fields, status=PolicyStatus.APPROVED, content_hash=policy_hash,
                            approval=approval(policy_hash))
    binding = dto(PolicyBinding, protection_version='fixture-v1', protection_hash=policy_hash,
                  risk_version='risk-v1', risk_hash=HASH, contract_version=CONTRACT_VERSION)
    source_document = dto(SourceDocument, source_format=SourceFormat.COLUMN_V1, source_version='1',
                          document=FrozenJSON({'version': '1', 'fixture': True}))
    source = dto(SourcePlanBinding, source_format=SourceFormat.MAINLINE1,
        source_version='mainline1.proposed.v1', source_plan_hash='sha256:' + HASH,
        source_record_ref='owner/plan', source_record_version='v1', source_trust=SourceTrust.SYNTHETIC,
        provenance_ref='fixture/provenance', approval_basis_ref=None, approval_basis_version=None,
        source_state='ready', source_environment='test', source_domain='domain/test', evaluation_ref='evaluation/fixture',
        scope_hash='sha256:' + HASH, parser_version='internal-table-v2', parser_config_hash='sha256:' + HASH,
        requirements_hash='sha256:' + HASH, operation_contract_version='original-snapshot-v1-proposed')
    sheet_scope = dto(SheetScope, sheet_id='csv:0', column_ids=('column:1',), row_ranges=((1, 2),), includes_header=True)
    scope = dto(TableScope, sheets=(sheet_scope,), coordinate_version='source-codepoint-half-open.v1')
    action = dto(ResolvedAction, action_id='action/1', source_operation_ref='operation/1', location=location,
                 category=Category.EMAIL, algorithm=algorithm, finding_refs=('finding/1',), requirement_refs=('requirement/1',))
    unresolved = dto(Unresolved, location=None, reason=ReasonCode.UNSUPPORTED_SCOPE, source_ref='source/unknown')
    plan_fields = dict(schema_version=ActionPlan.SCHEMA, plan_id='plan/1', asset_version='asset/v1',
        input_hash=HASH, scope=scope, actions=(action,), policy_binding=binding, unresolved=(),
        source=source, adapter_version='adapter-fixture-v1', created_at=AT, expires_at=AT + timedelta(hours=1),
        limits=BASELINE_LIMITS)
    plan_hash = content_hash(plan_fields)
    plan = ActionPlan(**plan_fields, plan_hash=plan_hash, approval=approval(plan_hash))
    key = dto(KeyReference, key_ref='enc-data/v1', purpose=KeyPurpose.DATA, version='v1', status=KeyStatus.ACTIVE)
    obj_context = dto(ObjectContext, project_ref='project/fixture', environment=Environment.TEST,
        object_uuid='00000000-0000-4000-8000-000000000001', object_version='v1', field_ref='document/body',
        authorization_ref='authorization/fixture')
    envelope = dto(CipherEnvelope, format_version='aes-256-gcm-hkdf-sha256.v1', key=key,
        kdf_salt=bytes(range(16)), nonce=bytes(range(12)), ciphertext_and_tag=bytes(range(32)))
    error = dto(ProtectionError, code=ReasonCode.AUTHORIZATION_DENIED, retryable=False, trace_id='trace/fixture')
    event = dto(SecurityEvent, event_id='event/1', kind=EventKind.PROTECTION, actor_ref='actor/1',
        object_ref='object/1', object_version='v1', outcome=Outcome.SUCCEEDED, occurred_at=AT,
        counts=(('processed', 1),), policy_binding=binding, algorithm_versions=('replace-v1',),
        key_versions=('enc-data/v1',), correlation_ref='trace/1', reason=None)
    event_v2 = SecurityEventV2(**{f.name: getattr(event, f.name) for f in fields(event)
                                 if f.name != 'schema_version'},
        schema_version=SecurityEventV2.SCHEMA, evidence_hashes=())
    audit = dto(AuditReceipt, event_id='event/1', durability=Durability.DURABLE, stored_at=AT,
        chain_version=None, entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
    checkpoint = dto(AuditCheckpoint, chain_identity=HASH,
        receipt=dto(AuditReceipt, event_id='event/1', durability=Durability.LEDGER_CONFIRMED, stored_at=AT,
            chain_version='ds.audit.v2', entry_ref='audit/v2/1', sequence=1, entry_hash=HASH, checkpoint_ref=None),
        checkpointed_at=AT, key=dto(KeyReference, key_ref='audit-auth/v1', purpose=KeyPurpose.AUDIT,
                                   version='v1', status=KeyStatus.ACTIVE), authentication=bytes(32))
    protected = dto(ProtectedResult, payload=payload, policy_binding=binding, coverage=coverage,
                    protection_version='protection-v1', trace_id='trace/fixture')
    execution = dto(ExecutionBinding, idempotency_key='idempotency/1', request_fingerprint=HASH,
        request_id='request/1', authorization_id='authorization/1', decision_id='decision/1',
        asset_version='asset/v1', execution_id='execution/1', reservation_id='reservation/1',
        subject_ref='actor/requester', domain_ref='domain/test', environment='test', scope=scope,
        quantity=10, quantity_unit=Unit.RECORD, expires_at=AT + timedelta(minutes=5), policy_binding=binding)
    quota = dto(QuotaReceipt, binding=execution, state=QuotaState.UNKNOWN, settled_amount=None,
                observed_at=AT, evidence_ref='evidence/unknown')
    recovery_event = dto(QuotaRecoveryEvent, event_id='event/recovery', kind=EventKind.AUTHORIZATION,
        actor_ref='actor/recovery', authorization_ref='authorization/recovery', operation='unknown', quota=quota,
        object_ref=execution.reservation_id, object_version=execution.asset_version,
        outcome=Outcome.UNKNOWN, occurred_at=AT, counts=(('unknown', execution.quantity),),
        policy_binding=binding, algorithm_versions=(), key_versions=(), correlation_ref=execution.execution_id,
        reason=None)
    report_fields = dict(schema_version=MaskReport.SCHEMA, execution_id='execution/1', executor_ref='executor/fixture',
        asset_version='asset/v1', source=source, action_plan_hash=plan_hash, input_hash=HASH, output_hash=HASH,
        ciphertext_hash=None, policy_binding=binding, algorithm_versions=('replace-v1',), coverage=coverage,
        hit_count=1, excluded=(), unresolved=(), rescan_state=ScanState.COMPLETE, rescan_coverage=coverage,
        outcome=Outcome.SUCCEEDED, created_at=AT)
    report = MaskReport(**report_fields, report_hash=content_hash(report_fields))
    report_proof = dto(ReportProof, report_hash=report.report_hash, execution_hash=content_hash(execution),
        context_hash=content_hash(obj_context), key=dto(KeyReference, key_ref='audit-auth/v1',
        purpose=KeyPurpose.AUDIT, version='v1', status=KeyStatus.ACTIVE), authentication=bytes(32))
    grant_fields = dict(schema_version=RevealGrant.SCHEMA, grant_id='grant/fixture', subject_ref='actor/requester',
        object_ref='object/1', object_version='v1', fields=((RevealField.EMAIL, 'users/email'),),
        purpose_ref='purpose/investigation', authorization_ref='authorization/1', issued_at=AT,
        expires_at=AT + timedelta(minutes=10))
    grant = RevealGrant(**grant_fields, approval=approval(content_hash(grant_fields)), state=GrantState.ACTIVE,
                        consumed_at=None, revoked_at=None)
    reveal_request = dto(RevealRequestRecord, request_ref='reveal-request-fixture',
        subject_ref=grant.subject_ref, course_id=1, object_ref=grant.object_ref,
        object_version=grant.object_version, fields=grant.fields, purpose_ref=grant.purpose_ref,
        reason=payload, requested_at=AT, state='approved', grant=grant,
        decided_by=grant.approval.approved_by, decided_at=AT, decision_event_ref=HASH)
    delivery = dto(DeliveryReceipt, binding=execution, outcome=Outcome.UNKNOWN, delivered_records=None,
                   evidence_ref='evidence/unknown', audit=audit)
    request = dto(AIRequest, endpoint_ref='official/fixture', model_ref='model/fixture', content=payload,
                  output_token_limit=1024, temperature=0.0)
    response = dto(AIResponse, content=payload, endpoint_ref='official/fixture', model_ref='model/fixture',
                   input_tokens=4, output_tokens=4, trace_id='trace/fixture')
    embedded = dto(EmbeddingResult, vectors=((0.0, 1.0),), endpoint_ref='official/fixture',
                   model_ref='model/fixture', trace_id='trace/fixture')
    stored = dto(StoredObject, object_ref='private/fixture', version='v1', ciphertext_hash=HASH,
                 size_bytes=32, state='candidate')
    file_operation = dto(FileUploadOperation, operation_ref='upload/fixture', actor_ref='actor/requester',
        scope_ref='resources/uploads', request_hash=HASH, object_uuid=obj_context.object_uuid,
        field_refs=('resources/file',), state='preparing', result_ref=None)
    backup_retention = dto(BackupRetentionRecord,
        backup=replace(stored, object_ref='backup/' + 'a' * 32, version='v2', state='verified'),
        created_at=AT, cadence='daily', files_hash=HASH, files_size=64)
    report_record = dto(ReportRecord, binding=execution, plan=plan, context=obj_context,
                        stored=stored, report=report, proof=report_proof)
    reveal_source = dto(RevealSource, object_ref=obj_context.object_uuid,
                        object_version=obj_context.object_version, fields=((obj_context, envelope),))
    canary = dto(CanarySeed, seed_id='0123456789abcdef0123456789abcdef', target_kind='knowledge',
        target_ref='synthetic/document', target_version='v1', environment=Environment.TEST, domain='domain/test')
    metric = dto(Metric, numerator=0, denominator=0, version='metric-v1', zero_reason=ReasonCode.UNSUPPORTED_SCOPE)
    for value in (context, payload, coverage, metric, location, finding, column, cell, snapshot, algorithm,
        policy.approval, teaching, rule, policy, binding, source_document, source, sheet_scope, scope, action,
        unresolved, plan, key, obj_context, envelope, error, event, audit, protected, execution, quota, report,
        report_proof, grant, delivery, request, response, embedded, stored, report_record, event_v2, checkpoint,
        recovery_event, canary, backup_retention, file_operation, reveal_source, reveal_request):
        objects[type(value)] = value
    return objects


def recovery_context(binding):
    """Explicit synthetic recovery principal, never a business-owner authorization."""
    return replace(examples()[ProtectionContext], actor_ref='actor/recovery',
        authorization_ref='authorization/recovery', environment=Environment(binding.environment),
        domain=binding.domain_ref, object_ref=binding.execution_id, object_version=binding.asset_version,
        scope_refs=(binding.reservation_id,), outlet=Outlet.AUDIT, purpose=Purpose.SECURITY_AUDIT)
