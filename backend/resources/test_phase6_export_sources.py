"""Restricted source authority on real PostgreSQL, separate from risk and target approval."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from threading import Event
import time
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuthenticatedAuditEntry
from data_security.adapters.persistence.models import ExportPlanApproval, ExportReport, PrivateObject, QuotaExecution
from data_security.contracts import ActionPlan, FrozenJSON, MediaType, ProtectionError, ReasonCode, SourceDocument, SourceFormat
from export_risk.models import ExecutionAuthorizationRecord, RiskDecision
from users.models import CTFUser

from .export_sources import document_hash
from .models import ExportSource, ExportSourcePermission
from .test_phase6_formal_fixtures import CONTENT, FormalResourceFixture, source_inputs


class ExportSourceOwnerTests(FormalResourceFixture, TransactionTestCase):
    def business_state(self):
        return tuple(list(model.objects.order_by('pk').values()) for model in (
            RiskDecision, ExecutionAuthorizationRecord, QuotaExecution, ExportReport, ExportPlanApproval))

    def test_registration_requires_explicit_live_add_permission_without_automatic_grants(self):
        resource = self.original()
        self.teacher.user_permissions.remove(Permission.objects.get(content_type__app_label='resources',
            codename='add_exportsource'))
        before = (AuthenticatedAuditEntry.objects.count(), self.business_state())
        result = self.register(resource)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(ExportSource.objects.count(), 0)
        self.assertEqual(ExportSourcePermission.objects.count(), 0)
        self.assertEqual((AuthenticatedAuditEntry.objects.count(), self.business_state()), before)
        CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
        self.assertEqual(self.register(resource).code, ReasonCode.AUTHORIZATION_DENIED)

    def test_complete_registration_pins_actual_original_asset_request_and_source_without_approval(self):
        resource = self.original()
        source_ref, receipt = self.ok(self.register(resource))
        row = ExportSource.objects.get(source_ref=source_ref)
        values = row.document
        original = resource.private_files['files']['file']
        self.assertEqual(receipt.chain_version, 'ds.audit.v2')
        self.assertEqual(values['original'], original['stored'])
        self.assertEqual(values['asset_version'], 'resource/' + original['context']['object_uuid'] + '/1')
        self.assertEqual(values['input_hash'], hashlib.sha256(CONTENT).hexdigest())
        self.assertEqual(values['source'], source_inputs()['source'].to_wire(include_payload=True))
        self.assertEqual(values['scope'], source_inputs()['scope'].to_wire())
        self.assertEqual(values['actions'], [item.to_wire() for item in source_inputs()['actions']])
        request = values['request']
        self.assertEqual((request['subject_id'], request['asset_version'], request['scope'],
                          request['record_count'], request['environment'], request['source_mode']),
                         ('user/' + str(self.teacher.pk), values['asset_version'],
                          ['resource/' + str(resource.pk)], 2, 'evaluation', 'evaluation'))
        initial = {**values, 'request': {**request, 'request_fingerprint': ''}}
        self.assertEqual(request['request_fingerprint'], document_hash(initial))
        self.assertEqual(row.document_hash, document_hash(values))
        self.assertEqual(values['risk_inputs'], {})
        self.assertEqual(values['policy_binding'], self.binding.to_wire())
        self.assertIsNone(row.approval)
        self.assertIsNone(row.plan_document)
        self.assertIsNone(row.execution_document)
        self.assertEqual(row.target_approval_ref, '')
        self.assertEqual(resource.status, 'pending')
        self.assertEqual(self.sources.inspect(user=self.reviewer, source_ref=source_ref).code,
                         ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.sources.grant(user=self.reviewer, source_ref=source_ref,
            grantee_id=self.teacher.pk, expires_at=timezone.now() + timedelta(minutes=1)).code,
            ReasonCode.AUTHORIZATION_DENIED)
        self.assertFalse(any(self.business_state()))

    def test_csv_interpretation_is_per_object_and_does_not_widen_the_upload_whitelist(self):
        resource = self.original()
        payload = self.ok(self.entry.uploads.read_original(user=self.teacher, resource_id=resource.pk))
        self.assertIs(payload.media_type, MediaType.BINARY)
        from .serializers import ResourceUploadSerializer
        from django.core.files.uploadedfile import SimpleUploadedFile
        invalid = ResourceUploadSerializer(data={'title': '合成资料', 'resource_type': 'document',
            'file': SimpleUploadedFile('synthetic.csv', payload.binary, content_type='text/csv')})
        self.assertFalse(invalid.is_valid())
        source_ref, _ = self.ok(self.register(resource))
        self.ok(self.sources.approve(user=self.reviewer, source_ref=source_ref))
        self.assertIs(self.ok(self.entry.uploads.read_original(user=self.teacher,
            resource_id=resource.pk)).media_type, MediaType.BINARY)

    def test_mainline_and_non_csv_or_partial_header_are_rejected_without_relabeling(self):
        resource = self.original()
        mainline = SourceDocument(schema_version=SourceDocument.SCHEMA,
            source_format=SourceFormat.MAINLINE1, source_version='mainline1.proposed.v1',
            document=FrozenJSON({'meta': {'schema_version': 'mainline1.proposed.v1'}}))
        legacy = source_inputs()['source']
        xlsx = replace(legacy, document=FrozenJSON({**legacy.document.to_value(), 'format': 'xlsx'}))
        for source in (mainline, xlsx):
            with self.subTest(source_format=source.source_format):
                self.assertEqual(self.register(resource, source=source).code, ReasonCode.SOURCE_NOT_APPROVED)
        scope = source_inputs()['scope']
        partial = replace(scope, sheets=(replace(scope.sheets[0], includes_header=False),))
        self.assertEqual(self.register(resource, scope=partial).code, ReasonCode.SCOPE_INCOMPLETE)
        self.assertFalse(ExportSource.objects.exists())
        self.assertFalse(any(self.business_state()))

    def test_source_approval_needs_a_second_actor_and_the_existing_original_acl(self):
        source_ref, _ = self.ok(self.register())
        self.teacher.user_permissions.add(Permission.objects.get(content_type__app_label='resources',
            codename='change_exportsource'))
        self.assertEqual(self.sources.approve(user=self.teacher, source_ref=source_ref).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        CTFUser.objects.filter(pk=self.reviewer.pk).update(is_staff=False)
        self.assertEqual(self.sources.approve(user=self.reviewer, source_ref=source_ref).code,
                         ReasonCode.AUTHORIZATION_DENIED)
        CTFUser.objects.filter(pk=self.reviewer.pk).update(is_staff=True)
        self.ok(self.sources.approve(user=self.reviewer, source_ref=source_ref))
        row = ExportSource.objects.get(source_ref=source_ref)
        plan = ActionPlan.from_wire(row.plan_document)
        raw_hash = hashlib.sha256(json.dumps(source_inputs()['source'].document.to_value(),
            ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        self.assertEqual(row.approval['content_hash'], raw_hash)
        self.assertEqual(plan.source.source_plan_hash, raw_hash)
        self.assertEqual(plan.source.source_state, 'not-declared')
        self.assertEqual(plan.source.approval_basis_ref, row.approval['approval_ref'])
        self.assertIsNone(plan.approval)
        self.assertEqual(len(plan.actions), 2)
        self.assertFalse(any(self.business_state()))

    def test_complete_m8_scope_and_all_declared_actions_must_match_before_source_approval(self):
        source_ref, _ = self.ok(self.register(actions=source_inputs()['actions'][:1]))
        before = AuthenticatedAuditEntry.objects.count()
        self.assertEqual(self.sources.approve(user=self.reviewer, source_ref=source_ref).code,
                         ReasonCode.SCOPE_INCOMPLETE)
        row = ExportSource.objects.get(source_ref=source_ref)
        self.assertIsNone(row.approval)
        self.assertIsNone(row.plan_document)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), before)
        self.assertFalse(any(self.business_state()))

    def test_current_use_is_exact_to_the_registered_requester_without_automatic_permissions(self):
        source_ref, _ = self.ok(self.register())
        self.ok(self.sources.approve(user=self.reviewer, source_ref=source_ref))
        before = set(self.teacher.user_permissions.values_list('pk', flat=True))
        self.assertEqual(self.sources.grant(user=self.reviewer, source_ref=source_ref,
            grantee_id=self.reviewer.pk, expires_at=timezone.now() + timedelta(minutes=1)).code,
            ReasonCode.AUTHORIZATION_DENIED)
        permission_ref, _ = self.ok(self.sources.grant(user=self.reviewer, source_ref=source_ref,
            grantee_id=self.teacher.pk, expires_at=timezone.now() + timedelta(minutes=1)))
        permission = ExportSourcePermission.objects.get(authorization_ref=permission_ref)
        self.assertEqual(permission.granted_by, 'user/' + str(self.reviewer.pk))
        self.assertEqual(permission.actor_ref, 'user/' + str(self.teacher.pk))
        self.assertEqual(permission.source_hash, ExportSource.objects.get(source_ref=source_ref).document_hash)
        self.assertEqual(set(self.teacher.user_permissions.values_list('pk', flat=True)), before)
        self.assertEqual(self.sources.load(user=self.reviewer, source_ref=source_ref,
            permission_ref=permission_ref).code, ReasonCode.AUTHORIZATION_DENIED)
        self.ok(self.sources.load(user=self.teacher, source_ref=source_ref, permission_ref=permission_ref))

    def test_loading_authenticates_full_source_and_one_grant_without_opening_original(self):
        source_ref, permission_ref = self.approved_source()
        reader = self.sources.read_event
        with patch.object(self.sources, 'read_event', wraps=reader) as verified, \
             patch.object(self.sources, 'read_original', side_effect=AssertionError('original opened during load')):
            row, document, plan, _ = self.ok(self.sources.load(user=self.teacher,
                source_ref=source_ref, permission_ref=permission_ref))
        self.assertEqual([call.args[0] for call in verified.call_args_list],
                         [source_ref + '/register', source_ref + '/approve', permission_ref + '/grant'])
        self.assertEqual(document.to_value(), row.document)
        self.assertEqual(plan.to_wire(), row.plan_document)
        self.assertFalse(any(self.business_state()))

    def test_current_plan_pin_and_active_requester_are_rechecked_without_audit_or_file_work(self):
        source_ref, permission_ref = self.approved_source()
        row, _, plan, _ = self.ok(self.sources.load(user=self.teacher,
            source_ref=source_ref, permission_ref=permission_ref))
        arguments = dict(user=self.teacher, source_ref=source_ref, permission_ref=permission_ref,
            expected_hash=row.document_hash, expected_plan=plan.to_wire())
        with patch.object(self.sources, 'read_event', side_effect=AssertionError('held-lock audit read')), \
             patch.object(self.sources, 'read_original', side_effect=AssertionError('held-lock original read')):
            self.assertIs(self.sources.authorize(**arguments), True)
            CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=False)
            self.assertEqual(self.sources.authorize(**arguments).code, ReasonCode.AUTHORIZATION_DENIED)
            CTFUser.objects.filter(pk=self.teacher.pk).update(is_active=True)
            ExportSource.objects.filter(pk=row.pk).update(plan_document={**row.plan_document, 'plan_id': 'changed/plan'})
            self.assertEqual(self.sources.authorize(**arguments).code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertFalse(any(self.business_state()))

    def test_recomputed_registration_hash_and_changed_grant_provenance_do_not_become_authority(self):
        source_ref, permission_ref = self.approved_source()
        row = ExportSource.objects.get(source_ref=source_ref)
        changed = {**row.document, 'request': {**row.document['request'], 'recipient_id': 'recipient/changed'}}
        ExportSource.objects.filter(pk=row.pk).update(document=changed, document_hash=document_hash(changed))
        self.assertEqual(self.sources.inspect(user=self.reviewer, source_ref=source_ref).code,
                         ReasonCode.AUDIT_UNAVAILABLE)
        ExportSource.objects.filter(pk=row.pk).update(document=row.document, document_hash=row.document_hash)
        ExportSourcePermission.objects.filter(authorization_ref=permission_ref).update(granted_by='user/other')
        self.assertEqual(self.sources.load(user=self.teacher, source_ref=source_ref,
            permission_ref=permission_ref).code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertFalse(any(self.business_state()))

    def test_revoked_source_or_current_use_never_grants_target_risk_or_delivery(self):
        source_ref, permission_ref = self.approved_source()
        before = self.business_state()
        receipt = self.ok(self.sources.revoke_permission(user=self.reviewer, permission_ref=permission_ref))
        self.assertLessEqual(len(receipt.event_id), 64)
        self.assertEqual(self.gateway.sink.read_authenticated(receipt.event_id).object_ref, permission_ref)
        self.assertEqual(self.sources.load(user=self.teacher, source_ref=source_ref,
            permission_ref=permission_ref).code, ReasonCode.SOURCE_NOT_APPROVED)
        receipt = self.ok(self.sources.revoke(user=self.reviewer, source_ref=source_ref))
        self.assertLessEqual(len(receipt.event_id), 64)
        self.assertEqual(self.gateway.sink.read_authenticated(receipt.event_id).object_ref, source_ref)
        self.assertEqual(self.sources.inspect(user=self.reviewer, source_ref=source_ref).code,
                         ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.business_state(), before)
        self.assertEqual(PrivateObject.objects.count(), 1)
        self.assertEqual(ExportSource.objects.count(), 1)
        self.assertEqual(ExportSourcePermission.objects.count(), 1)

    def test_source_and_approval_audit_failure_roll_back_only_their_own_short_transaction(self):
        resource = self.original()
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
            retryable=False, trace_id='test/source-audit')
        original_record = self.gateway.record
        def rejected(*args):
            self.ok(original_record(*args))
            return failure
        before = AuthenticatedAuditEntry.objects.count()
        with patch.object(self.gateway, 'record', side_effect=rejected):
            self.assertEqual(self.register(resource).code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(ExportSource.objects.count(), 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), before)
        source_ref, _ = self.ok(self.register(resource))
        before = AuthenticatedAuditEntry.objects.count()
        with patch.object(self.gateway, 'record', side_effect=rejected):
            self.assertEqual(self.sources.approve(user=self.reviewer, source_ref=source_ref).code,
                             ReasonCode.AUDIT_UNAVAILABLE)
        row = ExportSource.objects.get(source_ref=source_ref)
        self.assertIsNone(row.approval)
        self.assertIsNone(row.plan_document)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), before)
        self.assertEqual(PrivateObject.objects.count(), 1)
        self.assertFalse(any(self.business_state()))

    def test_use_deadline_is_read_after_real_postgresql_permission_lock_wait(self):
        deadline = timezone.now() + timedelta(seconds=3)
        source_ref, permission_ref = self.approved_source(expires_at=deadline)
        row, _, plan, _ = self.ok(self.sources.load(user=self.teacher,
            source_ref=source_ref, permission_ref=permission_ref))
        started = Event()
        holder = {}
        def authorize():
            try:
                with connections['default'].cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    holder['pid'] = cursor.fetchone()[0]
                started.set()
                return self.sources.authorize(user=self.teacher, source_ref=source_ref,
                    permission_ref=permission_ref, expected_hash=row.document_hash, expected_plan=plan.to_wire())
            finally:
                connections['default'].close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                ExportSourcePermission.objects.select_for_update().get(authorization_ref=permission_ref)
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    parent_pid = cursor.fetchone()[0]
                future = pool.submit(authorize)
                self.assertTrue(started.wait(5))
                until = time.monotonic() + 5
                blocked = False
                while time.monotonic() < until:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_stat_clear_snapshot()')
                        cursor.execute('SELECT %s = ANY(pg_blocking_pids(%s))', [parent_pid, holder['pid']])
                        blocked = cursor.fetchone()[0]
                    if blocked:
                        break
                    time.sleep(0.01)
                self.assertTrue(blocked, 'requester did not wait on the held source-use row')
                self.assertFalse(future.done())
                while timezone.now() <= deadline:
                    time.sleep(0.01)
            self.assertEqual(future.result(timeout=5).code, ReasonCode.AUTHORIZATION_EXPIRED)
        self.assertFalse(any(self.business_state()))
