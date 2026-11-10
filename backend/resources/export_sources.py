"""Restricted COLUMN_V1 source/request owner; no target, risk or quota authority."""
from dataclasses import replace
import hashlib
import json

from django.db import DatabaseError, connection, transaction

from data_security.contracts import (
    ActionPlan, Approval, AuditReceipt, ContractViolation, Durability, Environment, EventKind,
    ExecutionBinding, FrozenJSON, MediaType, ObjectContext, Outcome, PolicyBinding,
    ProtectionError, ReasonCode, ResolvedAction, SecurityEventV2, SourceDocument,
    SourceFormat, StoredObject, TableScope, canonical_bytes,
)
from data_security.contracts.schema import reference, require, utc
from users.models import CTFUser

from .models import ExportSource, ExportSourcePermission


def document_hash(value):
    return hashlib.sha256(canonical_bytes(FrozenJSON(value), include_payload=True)).hexdigest()


class ResourceExportSources:
    def __init__(self, *, read_references, read_original, freeze_request, build_plan,
                 audit, read_event, policy_binding, clock, identity):
        self.read_references, self.read_original = read_references, read_original
        self.freeze_request, self.build_plan = freeze_request, build_plan
        self.audit, self.read_event, self.policy_binding = audit, read_event, policy_binding
        self.clock, self.identity = clock, identity

    def _actor(self, user, capability=None):
        require(user.is_authenticated, ReasonCode.AUTHORIZATION_DENIED)
        actor = CTFUser.objects.filter(pk=user.pk, is_active=True).first()
        require(actor is not None and (capability is None or actor.has_perm(capability)),
                ReasonCode.AUTHORIZATION_DENIED)
        return actor

    def _audit(self, *, event_id, actor_ref, object_ref, source_ref, operation, metadata):
        event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
            event_id=event_id, kind=EventKind.AUTHORIZATION, actor_ref=actor_ref,
            object_ref=object_ref, object_version='1', outcome=Outcome.SUCCEEDED,
            occurred_at=self.clock(), counts=(('processed', 1),), policy_binding=self.policy_binding,
            algorithm_versions=('resource.export-source.v1', operation), key_versions=(),
            correlation_ref=source_ref, reason=None, evidence_hashes=(('report', document_hash(metadata)),))
        receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
        if isinstance(receipt, ProtectionError):
            require(False, receipt.code)
        require(type(receipt) is AuditReceipt and receipt.event_id == event_id and
                receipt.durability is Durability.LEDGER_CONFIRMED and receipt.chain_version == 'ds.audit.v2',
                ReasonCode.AUDIT_UNAVAILABLE)
        return receipt

    def _verify(self, *, event_id, actor_ref, object_ref, source_ref, operation, metadata):
        event = self.read_event(event_id)
        if isinstance(event, ProtectionError):
            require(False, event.code)
        require(type(event) is SecurityEventV2, ReasonCode.AUDIT_UNAVAILABLE)
        expected = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
            event_id=event_id, kind=EventKind.AUTHORIZATION, actor_ref=actor_ref,
            object_ref=object_ref, object_version='1', outcome=Outcome.SUCCEEDED,
            occurred_at=event.occurred_at, counts=(('processed', 1),), policy_binding=self.policy_binding,
            algorithm_versions=('resource.export-source.v1', operation), key_versions=(),
            correlation_ref=source_ref, reason=None, evidence_hashes=(('report', document_hash(metadata)),))
        require(event == expected, ReasonCode.AUDIT_UNAVAILABLE)

    def register(self, *, user, resource_id, source, scope, actions, request_fields, risk_inputs, expires_at):
        """Freeze the original and complete inputs. No approval or current-use grant is implied."""
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            actor = self._actor(user, 'resources.add_exportsource')
            require(type(source) is SourceDocument and source.source_format is SourceFormat.COLUMN_V1 and
                    source.document.to_value().get('format') == 'csv', ReasonCode.SOURCE_NOT_APPROVED)
            require(type(scope) is TableScope and len(scope.sheets) == 1 and
                    scope.sheets[0].sheet_id == 'csv:0' and scope.sheets[0].includes_header and
                    len(scope.sheets[0].row_ranges) == 1 and scope.sheets[0].row_ranges[0][0] == 1,
                    ReasonCode.SCOPE_INCOMPLETE)
            require(type(actions) is tuple and all(type(value) is ResolvedAction for value in actions),
                    ReasonCode.INVALID_TYPE)
            require(type(request_fields) is FrozenJSON and type(risk_inputs) is FrozenJSON, ReasonCode.INVALID_TYPE)
            utc(expires_at)
            require(self.clock() < expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
            references = self.read_references(user=actor, resource_id=resource_id)
            if isinstance(references, ProtectionError):
                return references
            _, context, original = references[0]
            require(context.environment is Environment.EVALUATION, ReasonCode.SOURCE_NOT_APPROVED)
            opened = self.read_original(user=actor, resource_id=resource_id)
            if isinstance(opened, ProtectionError):
                return opened
            source_ref = 'source/' + self.identity()
            asset_version = 'resource/' + context.object_uuid + '/' + original.version
            quantity = scope.sheets[0].row_ranges[0][1] - 1
            require(quantity > 0, ReasonCode.SCOPE_INCOMPLETE)
            request = self.freeze_request(request_fields, request_id='request/' + self.identity(),
                actor_ref='user/' + str(actor.pk), asset_version=asset_version,
                scope_ref='resource/' + str(resource_id), quantity=quantity)
            document = dict(schema_version='resource.export-source.v1', source_ref=source_ref,
                resource_id=str(resource_id), registered_by='user/' + str(actor.pk),
                original=original.to_wire(), context=context.to_wire(), asset_version=asset_version,
                input_hash=hashlib.sha256(opened.binary).hexdigest(), interpretation='csv',
                source=source.to_wire(include_payload=True), scope=scope.to_wire(),
                actions=[action.to_wire() for action in actions], request=request.to_value(),
                risk_inputs=risk_inputs.to_value(), policy_binding=self.policy_binding.to_wire())
            document['request']['request_fingerprint'] = document_hash(document)
            digest = document_hash(document)
            with transaction.atomic():
                self._actor(user, 'resources.add_exportsource')
                require(self.clock() < expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
                row = ExportSource.objects.create(source_ref=source_ref, resource_id=resource_id,
                    document=document, document_hash=digest, expires_at=expires_at)
                receipt = self._audit(event_id=source_ref + '/register', actor_ref=document['registered_by'],
                    object_ref=source_ref, source_ref=source_ref, operation='register',
                    metadata=dict(document_hash=digest, expires_at=expires_at.isoformat()))
            return row.source_ref, receipt
        except (ContractViolation, DatabaseError) as error:
            return self._failure(error, 'source/register')

    def approve(self, *, user, source_ref):
        """An explicit second actor approves the source and materializes M8's unapproved target plan."""
        try:
            reference(source_ref)
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            actor = self._actor(user, 'resources.change_exportsource')
            row = ExportSource.objects.filter(source_ref=source_ref).first()
            require(row is not None and row.approval is None and row.revoked_at is None,
                    ReasonCode.SOURCE_NOT_APPROVED)
            require(document_hash(row.document) == row.document_hash, ReasonCode.HASH_MISMATCH)
            require(row.document['registered_by'] != 'user/' + str(actor.pk), ReasonCode.AUTHORIZATION_DENIED)
            self._verify(event_id=source_ref + '/register', actor_ref=row.document['registered_by'],
                object_ref=source_ref, source_ref=source_ref, operation='register',
                metadata=dict(document_hash=row.document_hash, expires_at=row.expires_at.isoformat()))
            # Original authentication, full open and M8 conversion all precede held row locks.
            payload = self.read_original(user=actor, resource_id=row.resource_id)
            if isinstance(payload, ProtectionError):
                return payload
            approval = Approval(schema_version=Approval.SCHEMA, approval_ref=source_ref + '/approval',
                requested_by=row.document['registered_by'], approved_by='user/' + str(actor.pk),
                approved_at=self.clock(), content_hash=hashlib.sha256(json.dumps(
                    SourceDocument.from_wire(row.document['source']).document.to_value(),
                    ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False,
                ).encode('utf-8')).hexdigest())
            plan = self.build_plan(FrozenJSON(row.document), approval, row.expires_at, payload)
            if isinstance(plan, ProtectionError):
                return plan
            require(type(plan) is ActionPlan and plan.approval is None, ReasonCode.POLICY_NOT_APPROVED)
            with transaction.atomic():
                current = ExportSource.objects.select_for_update().get(pk=row.pk)
                self._actor(user, 'resources.change_exportsource')
                require(current.document_hash == row.document_hash and document_hash(current.document) == row.document_hash
                        and current.approval is None and current.revoked_at is None, ReasonCode.SOURCE_NOT_APPROVED)
                require(self.clock() < current.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
                current.approval, current.plan_document = approval.to_wire(), plan.to_wire()
                current.save(update_fields=['approval', 'plan_document'])
                receipt = self._audit(event_id=source_ref + '/approve', actor_ref=approval.approved_by,
                    object_ref=source_ref, source_ref=source_ref, operation='approve',
                    metadata=dict(document_hash=row.document_hash, approval=approval.to_wire(),
                                  plan_hash=plan.plan_hash, expires_at=row.expires_at.isoformat()))
            return source_ref, receipt
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, 'source/approve')

    def revoke(self, *, user, source_ref):
        try:
            reference(source_ref)
            with transaction.atomic():
                row = ExportSource.objects.select_for_update().filter(source_ref=source_ref).first()
                actor = self._actor(user, 'resources.change_exportsource')
                require(row is not None, ReasonCode.AUTHORIZATION_DENIED)
                if row.revoked_at is None:
                    row.revoked_at = self.clock()
                    row.save(update_fields=['revoked_at'])
                return self._audit(event_id='source-revoke/' + self.identity(),
                    actor_ref='user/' + str(actor.pk), object_ref=source_ref, source_ref=source_ref,
                    operation='revoke', metadata=dict(document_hash=row.document_hash,
                                                     revoked_at=row.revoked_at.isoformat()))
        except (ContractViolation, DatabaseError) as error:
            return self._failure(error, 'source/revoke')

    def grant(self, *, user, source_ref, grantee_id, expires_at):
        try:
            reference(source_ref)
            utc(expires_at)
            with transaction.atomic():
                row = ExportSource.objects.select_for_update().filter(source_ref=source_ref).first()
                actor = self._actor(user, 'resources.add_exportsourcepermission')
                grantee = CTFUser.objects.filter(pk=grantee_id, is_active=True).first()
                require(row is not None and row.approval is not None and row.revoked_at is None and
                        grantee is not None and row.document['request']['subject_id'] == 'user/' + str(grantee.pk),
                        ReasonCode.AUTHORIZATION_DENIED)
                require(self.clock() < expires_at <= row.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
                permission = ExportSourcePermission.objects.create(authorization_ref='source-use/' + self.identity(),
                    source=row, actor_ref='user/' + str(grantee.pk), source_hash=row.document_hash,
                    granted_by='user/' + str(actor.pk), expires_at=expires_at)
                metadata = self._permission_metadata(permission)
                receipt = self._audit(event_id=permission.authorization_ref + '/grant', actor_ref=metadata['granted_by'],
                    object_ref=permission.authorization_ref, source_ref=source_ref, operation='grant', metadata=metadata)
            return permission.authorization_ref, receipt
        except (ContractViolation, DatabaseError) as error:
            return self._failure(error, 'source/grant')

    def revoke_permission(self, *, user, permission_ref):
        try:
            reference(permission_ref)
            with transaction.atomic():
                permission = ExportSourcePermission.objects.select_for_update().filter(
                    authorization_ref=permission_ref).first()
                actor = self._actor(user, 'resources.change_exportsourcepermission')
                require(permission is not None, ReasonCode.AUTHORIZATION_DENIED)
                if permission.revoked_at is None:
                    permission.revoked_at = self.clock()
                    permission.save(update_fields=['revoked_at'])
                return self._audit(event_id='source-use-revoke/' + self.identity(),
                    actor_ref='user/' + str(actor.pk), object_ref=permission_ref,
                    source_ref=permission.source.source_ref, operation='revoke-use',
                    metadata=self._permission_metadata(permission))
        except (ContractViolation, DatabaseError) as error:
            return self._failure(error, 'source/revoke-use')

    def _permission_metadata(self, permission):
        return dict(authorization_ref=permission.authorization_ref, source_ref=permission.source.source_ref,
            actor_ref=permission.actor_ref, source_hash=permission.source_hash, granted_by=permission.granted_by,
            expires_at=permission.expires_at.isoformat(),
            revoked_at=permission.revoked_at.isoformat() if permission.revoked_at else None)

    def _authorized(self, *, user, source_ref, permission_ref, expected_hash=None):
        reference(source_ref)
        reference(permission_ref)
        with transaction.atomic():
            row = ExportSource.objects.select_for_update().filter(source_ref=source_ref).first()
            permission = ExportSourcePermission.objects.select_for_update().filter(
                authorization_ref=permission_ref).first()
            actor = self._actor(user)
            require(row is not None and permission is not None and permission.source_id == row.pk and
                    permission.actor_ref == 'user/' + str(actor.pk) == row.document['request']['subject_id'] and
                    permission.source_hash == row.document_hash and
                    (expected_hash is None or row.document_hash == expected_hash), ReasonCode.AUTHORIZATION_DENIED)
            require(row.approval is not None and row.plan_document is not None and
                    row.revoked_at is None and permission.revoked_at is None, ReasonCode.SOURCE_NOT_APPROVED)
            require(document_hash(row.document) == row.document_hash, ReasonCode.HASH_MISMATCH)
            require(self.clock() < min(row.expires_at, permission.expires_at), ReasonCode.AUTHORIZATION_EXPIRED)
        return row, permission

    def authorize(self, *, user, source_ref, permission_ref, expected_hash, expected_plan):
        """Fresh exact source use, without file/crypto/audit reads inside the flow UoW."""
        try:
            with transaction.atomic():
                row, _ = self._authorized(user=user, source_ref=source_ref, permission_ref=permission_ref,
                                          expected_hash=expected_hash)
                require(row.plan_document == expected_plan, ReasonCode.SOURCE_NOT_APPROVED)
            return True
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, 'source/authorize')

    def _registered(self, row):
        document = FrozenJSON(row.document)
        values = document.to_value()
        require(values['schema_version'] == 'resource.export-source.v1' and
                values['source_ref'] == row.source_ref and values['resource_id'] == str(row.resource_id) and
                values['interpretation'] == 'csv' and document_hash(values) == row.document_hash,
                ReasonCode.REPORT_MISMATCH)
        source = SourceDocument.from_wire(values['source'])
        require(source.source_format is SourceFormat.COLUMN_V1, ReasonCode.SOURCE_NOT_APPROVED)
        plan = ActionPlan.from_wire(row.plan_document)
        approval = Approval.from_wire(row.approval)
        require(plan.source.approval_basis_ref == approval.approval_ref and
                plan.source.source_record_ref == row.source_ref and
                plan.source.source_environment == 'evaluation' and plan.approval is None,
                ReasonCode.SOURCE_NOT_APPROVED)
        self._verify(event_id=row.source_ref + '/register', actor_ref=values['registered_by'],
            object_ref=row.source_ref, source_ref=row.source_ref, operation='register',
            metadata=dict(document_hash=row.document_hash, expires_at=row.expires_at.isoformat()))
        self._verify(event_id=row.source_ref + '/approve', actor_ref=approval.approved_by,
            object_ref=row.source_ref, source_ref=row.source_ref, operation='approve',
            metadata=dict(document_hash=row.document_hash, approval=approval.to_wire(),
                          plan_hash=plan.plan_hash, expires_at=row.expires_at.isoformat()))
        return document, plan

    def inspect(self, *, user, source_ref):
        """Permissioned review of retained authority; no current-use grant or original open."""
        try:
            reference(source_ref)
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            self._actor(user, 'resources.view_exportsource')
            row = ExportSource.objects.filter(source_ref=source_ref).first()
            require(row is not None and row.approval is not None and row.plan_document is not None and
                    row.revoked_at is None, ReasonCode.SOURCE_NOT_APPROVED)
            require(self.clock() < row.expires_at, ReasonCode.AUTHORIZATION_EXPIRED)
            document, plan = self._registered(row)
            return row, document, plan
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, 'source/inspect')

    def load(self, *, user, source_ref, permission_ref):
        """Authenticate and re-fetch the complete owner document, not an ExecutionBinding substitute."""
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            row, permission = self._authorized(user=user, source_ref=source_ref, permission_ref=permission_ref)
            document, plan = self._registered(row)
            values = document.to_value()
            self._verify(event_id=permission_ref + '/grant', actor_ref=permission.granted_by,
                object_ref=permission_ref, source_ref=source_ref, operation='grant',
                metadata=self._permission_metadata(permission))
            references = self.read_references(user=user, resource_id=row.resource_id)
            if isinstance(references, ProtectionError):
                return references
            _, context, original = references[0]
            require(original == StoredObject.from_wire(values['original']) and
                    (context.project_ref, context.environment.value, context.object_uuid, context.object_version,
                     context.field_ref) == tuple(values['context'][key] for key in (
                         'project_ref', 'environment', 'object_uuid', 'object_version', 'field_ref')) and
                    values['asset_version'] == 'resource/' + context.object_uuid + '/' + original.version and
                    plan.asset_version == values['asset_version'] and plan.input_hash == values['input_hash'] and
                    plan.scope == TableScope.from_wire(values['scope']) and
                    plan.policy_binding == PolicyBinding.from_wire(values['policy_binding']) == self.policy_binding,
                    ReasonCode.REPORT_MISMATCH)
            return row, document, plan, permission.expires_at
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, 'source/load')

    def load_input(self, *, user, source_ref, permission_ref, expected_hash, plan, binding, context):
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block, ReasonCode.DELIVERY_UNKNOWN)
            row, _ = self._authorized(user=user, source_ref=source_ref, permission_ref=permission_ref,
                                      expected_hash=expected_hash)
            require(plan.plan_hash == ActionPlan.from_wire(row.plan_document).plan_hash and
                    binding.request_fingerprint == row.document['request']['request_fingerprint'],
                    ReasonCode.REPORT_MISMATCH)
            payload = self.read_original(user=user, resource_id=row.resource_id)
            if isinstance(payload, ProtectionError):
                return payload
            require(hashlib.sha256(payload.binary).hexdigest() == row.document['input_hash'], ReasonCode.HASH_MISMATCH)
            # The per-object approved interpretation never changes the global TXT/upload policy.
            return replace(payload, media_type=MediaType.CSV)
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, 'source/input')

    def retain_execution(self, *, user, source_ref, permission_ref, risk_permission_ref, binding, context):
        try:
            reference(risk_permission_ref)
            require(type(binding) is ExecutionBinding and type(context) is ObjectContext, ReasonCode.INVALID_TYPE)
            with transaction.atomic():
                row, permission = self._authorized(user=user, source_ref=source_ref, permission_ref=permission_ref)
                request = row.document['request']
                plan = ActionPlan.from_wire(row.plan_document)
                require((binding.request_id, binding.request_fingerprint, binding.subject_ref,
                         binding.asset_version, binding.quantity, binding.environment, binding.scope,
                         binding.policy_binding, binding.domain_ref, context.environment.value,
                         context.project_ref, context.object_version, context.field_ref, context.authorization_ref) ==
                        (request['request_id'], request['request_fingerprint'], request['subject_id'],
                         request['asset_version'], request['record_count'], 'evaluation', plan.scope,
                         plan.policy_binding, plan.source.source_domain, 'evaluation',
                         row.document['context']['project_ref'], plan.asset_version, 'resources/export',
                         binding.authorization_id), ReasonCode.REPORT_MISMATCH)
                require(plan.created_at < binding.expires_at <= min(row.expires_at, permission.expires_at),
                        ReasonCode.AUTHORIZATION_EXPIRED)
                document = dict(binding=binding.to_wire(), context=context.to_wire(),
                                risk_permission_ref=risk_permission_ref)
                if row.execution_document is not None:
                    require(row.execution_document == document, ReasonCode.IDEMPOTENCY_CONFLICT)
                else:
                    row.execution_document = document
                    row.save(update_fields=['execution_document'])
            return binding
        except (ContractViolation, DatabaseError) as error:
            return self._failure(error, 'source/execution')

    def target(self, *, user, source_ref):
        """Explicit metadata view for target review; not source use or a file read."""
        try:
            retained = self.inspect(user=user, source_ref=source_ref)
            if isinstance(retained, ProtectionError):
                return retained
            row, _, plan = retained
            require(row.execution_document is not None, ReasonCode.AUTHORIZATION_DENIED)
            return row, plan
        except (ContractViolation, DatabaseError, KeyError, TypeError, ValueError) as error:
            return self._failure(error, 'source/target')

    def retain_target(self, *, user, source_ref, approval_ref):
        try:
            reference(approval_ref)
            with transaction.atomic():
                self._actor(user, 'security_policies.add_exportplanapproval')
                row = ExportSource.objects.select_for_update().get(source_ref=source_ref)
                require(not row.target_approval_ref or row.target_approval_ref == approval_ref,
                        ReasonCode.IDEMPOTENCY_CONFLICT)
                row.target_approval_ref = approval_ref
                row.save(update_fields=['target_approval_ref'])
            return approval_ref
        except (ContractViolation, DatabaseError) as error:
            return self._failure(error, 'source/target-reference')

    @staticmethod
    def _failure(error, trace):
        code = (error.code if isinstance(error, ContractViolation) else
                ReasonCode.DELIVERY_UNKNOWN if isinstance(error, DatabaseError) else ReasonCode.REPORT_MISMATCH)
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code, retryable=False, trace_id=trace)
