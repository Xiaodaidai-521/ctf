"""New PG reveal-read tests; trusted approved rows are seeded, not an approval UI.

Uses B, real field storage, current owner permissions, M3 and ds.audit.v2. No
SQLite, external provider, historical data or globally pre-bound test entrance.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble, assemble_reveal
from data_security.adapters.persistence import fields as field_module
from data_security.adapters.persistence.models import RevealRequest
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import (
    Approval, AuditReceipt, BoundedPayload, CipherEnvelope, Durability, Environment,
    EventKind, GrantState, KeyStatus, Outcome, Outlet, ProtectionContext, ProtectionError,
    Purpose, ReasonCode, RevealField, RevealGrant, RevealSource, Role, SecurityEventV2, content_hash,
)
from data_security.tests.phase4_fixtures import field_configuration
from learning_paths.models import LearningPath
from legal.models import LegalAnalysisTask, LegalFactSnapshot, LegalReport
from users.models import CTFUser, CourseDataGrant

MARKER = 'reveal-private@example.invalid'


class RevealPostgresTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL, never SQLite')
        files = field_configuration()
        self.path, self.config, _, _ = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        checkpoints = self.path.parent / 'reveal-checkpoints'
        checkpoints.mkdir(mode=0o700)
        self.config['audit_chain'] = {
            'chain_version': 'ds.audit.v2', 'project_ref': 'phase7/reveal-synthetic',
            'object_uuid': '00000000-0000-4000-8000-000000000007', 'object_version': 'v1',
            'authorization_ref': 'authorization/phase7-reveal-synthetic', 'retained_keys': [],
            'checkpoint_root': str(checkpoints), 'checkpoint_ref': None,
        }
        self.path.write_text(json.dumps(self.config))
        self.components = assemble(config_path=self.path)
        previous = field_module._adapter
        self.addCleanup(field_module.bind_field_storage, previous)
        field_module.bind_field_storage(self.components['fields'])
        self.requester = CTFUser.objects.create_user(username='reveal-owner', email=MARKER, role='student')
        self.reviewer = CTFUser.objects.create_user(username='reveal-reviewer', role='teacher', is_staff=True)
        self.admin = CTFUser.objects.create_user(username='reveal-other-admin', role='admin',
                                                is_staff=True, is_superuser=True)
        self.course = LearningPath.objects.create(title='合成课程', slug='reveal-synthetic',
                                                   description='合成课程', difficulty='AP')
        self.access = CourseDataGrant.objects.create(actor=self.reviewer, student=self.requester,
            course=self.course, granted_by=self.reviewer, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    def seed(self, *, target=None, field=RevealField.EMAIL, field_ref='users.ctfuser/email',
             approver=None, issued_at=None):
        target = self.requester if target is None else target
        approver = self.reviewer if approver is None else approver
        issued_at = issued_at or datetime.now(timezone.utc)
        reference = 'reveal/' + uuid4().hex
        values = dict(schema_version=RevealGrant.SCHEMA, grant_id=reference,
            subject_ref='user/' + str(self.requester.pk), object_ref=str(target.security_uuid),
            object_version='v' + str(target.security_revision), fields=((field, field_ref),),
            purpose_ref='purpose/investigation', authorization_ref='authorization/' + reference,
            issued_at=issued_at, expires_at=issued_at + timedelta(seconds=900))
        approval = Approval(schema_version=Approval.SCHEMA, approval_ref='approval/' + reference,
            requested_by=values['subject_ref'], approved_by='user/' + str(approver.pk),
            approved_at=issued_at, content_hash=content_hash(values))
        grant = RevealGrant(**values, approval=approval, state=GrantState.ACTIVE,
                            consumed_at=None, revoked_at=None)
        row = RevealRequest.objects.create(requested_by=self.requester, approved_by=approver,
            course_id=self.course.pk, object_ref=grant.object_ref, object_version=grant.object_version,
            fields=grant.to_wire()['fields'], purpose_ref=grant.purpose_ref, reason='合成资料核对',
            requested_at=issued_at, grant_id=grant.grant_id, grant_document=grant.to_wire(), state='approved')
        context = ProtectionContext(schema_version=ProtectionContext.SCHEMA,
            actor_ref=grant.subject_ref, authorization_ref=grant.authorization_ref,
            scope_refs=(field_ref,), environment=Environment.EVALUATION, domain='ctf', outlet=Outlet.API,
            purpose=Purpose.INVESTIGATION, role=Role(self.requester.role), object_ref=grant.object_ref,
            object_version=grant.object_version, source_ref=None, source_version=None,
            source_hash=None, trace_id='trace/' + uuid4().hex)
        return grant, row, context

    def reveal(self, grant, context):
        return assemble_reveal(components=self.components).reveal(grant, context)

    def event(self, grant):
        documents = SecurityAuditRecord.objects.filter(event__correlation_ref=grant.grant_id)
        self.assertEqual(documents.count(), 1)
        event = SecurityEventV2.from_wire(documents.get().event)
        self.assertEqual(self.components['audit'].sink.read_authenticated(event.event_id), event)
        self.assertNotIn(MARKER, json.dumps(event.to_wire()))
        return event

    def test_consumes_locked_grant_before_field_decryption_and_authenticated_commit(self):
        self.requester.bio = '合成更新'
        self.requester.save(update_fields=['bio'])
        grant, row, context = self.seed()
        original = deepcopy(self.requester.security_envelopes)
        opened_contexts, receipts = [], []
        real_open = self.components['crypto'].open
        real_record = self.components['audit'].record

        def open_field(envelope, storage_context, key):
            self.assertEqual(RevealRequest.objects.get(pk=row.pk).state, 'consumed')
            self.assertTrue(connection.in_atomic_block)
            opened_contexts.append(storage_context)
            return real_open(envelope, storage_context, key)

        def record(event, durability):
            self.assertEqual(RevealRequest.objects.get(pk=row.pk).state, 'consumed')
            self.assertTrue(connection.in_atomic_block)
            receipt = real_record(event, durability)
            receipts.append(receipt)
            return receipt

        with patch.object(self.components['crypto'], 'open', side_effect=open_field), \
                patch.object(self.components['audit'], 'record', side_effect=record):
            result = self.reveal(grant, context)
        self.assertIsInstance(result, BoundedPayload)
        self.assertEqual(result.tree.to_value(), {'users.ctfuser/email': MARKER})
        row.refresh_from_db()
        self.assertEqual(row.state, 'consumed')
        self.assertGreaterEqual(row.consumed_at, grant.issued_at)
        self.assertFalse(connection.in_atomic_block)
        self.assertEqual(len(opened_contexts), 1)
        self.assertEqual(opened_contexts[0].object_version, 'v1')
        self.assertEqual(grant.object_version, 'v2')
        self.assertEqual(opened_contexts[0].authorization_ref, 'authorization/phase4-storage')
        self.assertEqual(CTFUser.objects.get(pk=self.requester.pk).security_envelopes, original)
        self.assertEqual(CTFUser.objects.get(pk=self.requester.pk).email, '')
        self.assertEqual(len(receipts), 1)
        self.assertIsInstance(receipts[0], AuditReceipt)
        self.assertIs(receipts[0].durability, Durability.LEDGER_CONFIRMED)
        self.assertEqual(receipts[0].chain_version, 'ds.audit.v2')
        event = self.event(grant)
        self.assertIs(event.kind, EventKind.REVEAL)
        self.assertIs(event.outcome, Outcome.SUCCEEDED)
        self.assertEqual(event.counts, (('records', 1),))
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_current_data_grant_and_both_active_owners_are_required(self):
        cases = ('requester-inactive', 'reviewer-inactive', 'course-revoked', 'course-expired')
        for case in cases:
            with self.subTest(case=case):
                grant, row, context = self.seed()
                if case in ('requester-inactive', 'reviewer-inactive'):
                    actor = self.requester if case == 'requester-inactive' else self.reviewer
                    CTFUser.objects.filter(pk=actor.pk).update(is_active=False)
                else:
                    CourseDataGrant.objects.filter(pk=self.access.pk).update(
                        active=case != 'course-revoked',
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=1 if case == 'course-revoked' else -1))
                with patch.object(self.components['crypto'], 'open') as opened:
                    result = self.reveal(grant, context)
                    opened.assert_not_called()
                self.assertIs(result.code, ReasonCode.AUTHORIZATION_DENIED)
                row.refresh_from_db()
                self.assertEqual(row.state, 'approved')
                self.assertIsNone(row.consumed_at)
                self.assertIs(self.event(grant).outcome, Outcome.DENIED)
                CTFUser.objects.filter(pk__in=(self.requester.pk, self.reviewer.pk)).update(is_active=True)
                CourseDataGrant.objects.filter(pk=self.access.pk).update(active=True,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    def test_role_spoof_or_admin_without_object_scope_cannot_read_originals(self):
        for case in ('spoofed-role', 'unscoped-admin'):
            with self.subTest(case=case):
                grant, row, context = self.seed(approver=self.admin if case == 'unscoped-admin' else None)
                if case == 'spoofed-role':
                    context = replace(context, role=Role.ADMIN)
                with patch.object(self.components['crypto'], 'open') as opened:
                    result = self.reveal(grant, context)
                    opened.assert_not_called()
                self.assertIs(result.code, ReasonCode.AUTHORIZATION_DENIED)
                row.refresh_from_db()
                self.assertEqual(row.state, 'approved')
                self.assertIs(self.event(grant).outcome, Outcome.DENIED)

    def test_revocation_expiry_version_and_changed_server_scope_are_rejected(self):
        for case in ('revoked', 'expired', 'version-changed', 'server-fields-changed', 'server-object-changed'):
            with self.subTest(case=case):
                grant, row, context = self.seed(issued_at=datetime.now(timezone.utc) - timedelta(minutes=16)
                                               if case == 'expired' else None)
                if case == 'revoked':
                    row.state, row.revoked_at = 'revoked', datetime.now(timezone.utc)
                    row.save(update_fields=['state', 'revoked_at'])
                elif case == 'version-changed':
                    self.requester.bio = '合成版本更新'
                    self.requester.save(update_fields=['bio'])
                elif case == 'server-fields-changed':
                    row.fields = [[RevealField.EMAIL.value, 'users.ctfuser/password']]
                    row.save(update_fields=['fields'])
                elif case == 'server-object-changed':
                    row.object_ref = str(self.admin.security_uuid)
                    row.save(update_fields=['object_ref'])
                with patch.object(self.components['crypto'], 'open') as opened:
                    result = self.reveal(grant, context)
                    opened.assert_not_called()
                self.assertIs(result.code, ReasonCode.AUTHORIZATION_EXPIRED if case == 'expired'
                              else ReasonCode.AUTHORIZATION_DENIED)
                row.refresh_from_db()
                self.assertEqual(row.state, 'revoked' if case == 'revoked' else 'approved')
                self.assertIsNone(row.consumed_at)
                self.assertIs(self.event(grant).outcome, Outcome.DENIED)

    def test_unsupported_secret_conversation_manual_and_non_ciphertext_scopes_stay_closed(self):
        cases = ((RevealField.EMAIL, 'users.ctfuser/password'),
            (RevealField.EMAIL, 'users.ctfuser/api_key'),
            (RevealField.CONVERSATION, 'ai_assistant.aimessage/content'),
            (RevealField.EVIDENCE, 'legal.legalfactsnapshot/manual_notes'),
            (RevealField.EVIDENCE, 'legal.legalevidence/excerpt'))
        for category, reference in cases:
            with self.subTest(reference=reference):
                grant, row, context = self.seed(field=category, field_ref=reference)
                with patch.object(self.components['crypto'], 'open') as opened:
                    result = self.reveal(grant, context)
                    opened.assert_not_called()
                self.assertIs(result.code, ReasonCode.UNSUPPORTED_SCOPE)
                row.refresh_from_db()
                self.assertEqual(row.state, 'approved')
                self.assertIs(self.event(grant).outcome, Outcome.DENIED)

    def test_legacy_or_missing_read_key_sources_cannot_fall_back_to_plain_columns(self):
        grant, row, context = self.seed()
        with patch.dict(self.components['fields'].read_keys, clear=True), \
                patch.object(self.components['crypto'], 'open') as opened:
            result = self.reveal(grant, context)
            opened.assert_not_called()
        self.assertIs(result.code, ReasonCode.KEY_UNAVAILABLE)
        row.refresh_from_db()
        self.assertEqual(row.state, 'approved')
        self.assertIs(self.event(grant).outcome, Outcome.FAILED)
        with patch.object(field_module, '_adapter', None):
            CTFUser.objects.filter(pk=self.requester.pk).update(security_state='legacy-v0', email=MARKER)
        grant, row, context = self.seed()
        self.components['fields'].legacy_reads = True
        with patch.object(self.components['crypto'], 'open') as opened:
            result = self.reveal(grant, context)
            opened.assert_not_called()
        self.assertIs(result.code, ReasonCode.SOURCE_NOT_APPROVED)
        row.refresh_from_db()
        self.assertEqual(row.state, 'approved')
        self.assertIs(self.event(grant).outcome, Outcome.DENIED)

    def test_bad_ciphertext_rolls_back_consumption_and_success_ledger_events(self):
        grant, row, context = self.seed()
        entries = deepcopy(self.requester.security_envelopes)
        envelope = CipherEnvelope.from_wire(entries['email']['envelope'])
        changed = replace(envelope, ciphertext_and_tag=envelope.ciphertext_and_tag[:-1] +
                          bytes([envelope.ciphertext_and_tag[-1] ^ 1]))
        entries['email']['envelope'] = changed.to_wire()
        with connection.cursor() as cursor:
            cursor.execute('UPDATE users_ctfuser SET security_envelopes=%s WHERE id=%s',
                           (json.dumps(entries), self.requester.pk))
        result = self.reveal(grant, context)
        self.assertIs(result.code, ReasonCode.CIPHERTEXT_INVALID)
        row.refresh_from_db()
        self.assertEqual(row.state, 'approved')
        self.assertIsNone(row.consumed_at)
        self.assertIs(self.event(grant).outcome, Outcome.FAILED)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_weak_or_missing_receipt_rolls_back_before_durable_failure_event(self):
        real_record = self.components['audit'].record
        for mode in ('missing', 'durable', 'v1', 'wrong-event', 'raise'):
            with self.subTest(mode=mode):
                grant, row, context = self.seed()
                before = AuthenticatedAuditEntry.objects.count()

                def record(event, durability):
                    receipt = real_record(event, durability)
                    if event.outcome is not Outcome.SUCCEEDED:
                        self.assertFalse(connection.in_atomic_block)
                        return receipt
                    self.assertTrue(connection.in_atomic_block)
                    if mode == 'missing':
                        return None
                    if mode == 'durable':
                        return replace(receipt, durability=Durability.DURABLE, chain_version=None,
                                       entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
                    if mode == 'v1':
                        return replace(receipt, chain_version='v1', checkpoint_ref=None)
                    if mode == 'wrong-event':
                        return replace(receipt, event_id='a' * 64)
                    raise RuntimeError(MARKER)

                with patch.object(self.components['audit'], 'record', side_effect=record):
                    result = self.reveal(grant, context)
                self.assertIs(result.code, ReasonCode.AUDIT_UNAVAILABLE)
                self.assertNotIn(MARKER, repr(result))
                row.refresh_from_db()
                self.assertEqual(row.state, 'approved')
                self.assertIsNone(row.consumed_at)
                self.assertIs(self.event(grant).outcome, Outcome.FAILED)
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), before + 1)

    def test_retained_read_only_key_reads_original_envelope_without_resealing(self):
        grant, row, context = self.seed()
        original = deepcopy(self.requester.security_envelopes)
        old = deepcopy(self.config['data_key'])
        retained = dict(old, status=KeyStatus.READ_ONLY.value)
        new = dict(old, key_ref='enc-data/v2', version='v2')
        key_path = self.path.parent / 'reveal-data-v2.key'
        key_path.write_bytes(secrets.token_bytes(32))
        key_path.chmod(0o600)
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_bytes())
        for entry in manifest['entries']:
            if entry['reference'] == old:
                entry['reference'] = retained
        manifest['entries'].append({'reference': new, 'file': key_path.name, 'identities': ['service/security']})
        manifest_path.write_text(json.dumps(manifest))
        self.config['data_key'] = new
        self.config['retained_data_keys'] = [retained]
        self.config['field_storage']['read_keys'] = [retained]
        self.path.write_text(json.dumps(self.config))
        self.components = assemble(config_path=self.path)
        field_module.bind_field_storage(self.components['fields'])
        with patch.object(self.components['crypto'], 'seal') as sealed:
            result = self.reveal(grant, context)
            sealed.assert_not_called()
        self.assertEqual(result.tree.to_value(), {'users.ctfuser/email': MARKER})
        self.assertEqual(CTFUser.objects.get(pk=self.requester.pk).security_envelopes, original)
        self.assertEqual(self.event(grant).key_versions, ('enc-data/v1',))
        row.refresh_from_db()
        self.assertEqual(row.state, 'consumed')

    def test_two_postgres_consumers_have_one_success_and_a_replay_denial(self):
        grant, row, context = self.seed()
        start = Event()

        def consume(number):
            close_old_connections()
            try:
                self.assertTrue(start.wait(10))
                return self.reveal(grant, replace(context, trace_id=context.trace_id + '/' + str(number)))
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(consume, number) for number in (1, 2)]
            start.set()
            results = [future.result(timeout=60) for future in futures]
        self.assertEqual(sum(isinstance(result, BoundedPayload) for result in results), 1)
        denied = [result for result in results if isinstance(result, ProtectionError)]
        self.assertEqual(len(denied), 1)
        self.assertIs(denied[0].code, ReasonCode.AUTHORIZATION_DENIED)
        row.refresh_from_db()
        self.assertEqual(row.state, 'consumed')
        events = [SecurityEventV2.from_wire(document) for document in
                  SecurityAuditRecord.objects.filter(event__correlation_ref=grant.grant_id).values_list('event', flat=True)]
        self.assertEqual(sorted(event.outcome.value for event in events), ['denied', 'succeeded'])
        for event in events:
            self.assertEqual(self.components['audit'].sink.read_authenticated(event.event_id), event)
            self.assertNotIn(MARKER, json.dumps(event.to_wire()))
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_expiry_is_rechecked_after_postgres_grant_lock_wait(self):
        # Keep the synthetic reveal clock behind the real audit receipt clock.
        grant, row, context = self.seed(issued_at=datetime.now(timezone.utc) - timedelta(minutes=16))
        now = [grant.issued_at + timedelta(seconds=1)]
        self.components['clock'] = lambda: now[0]
        attempting_lock = Event()

        def execute(execute, sql, params, many, db_context):
            if 'security_policies_revealrequest' in sql and 'FOR UPDATE' in sql:
                attempting_lock.set()
            return execute(sql, params, many, db_context)

        def consume():
            close_old_connections()
            try:
                with connection.execute_wrapper(execute):
                    return self.reveal(grant, context)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                RevealRequest.objects.select_for_update().get(pk=row.pk)
                future = pool.submit(consume)
                self.assertTrue(attempting_lock.wait(10))
                now[0] = grant.expires_at
            result = future.result(timeout=60)
        self.assertIs(result.code, ReasonCode.AUTHORIZATION_EXPIRED)
        row.refresh_from_db()
        self.assertEqual(row.state, 'approved')
        self.assertIsNone(row.consumed_at)
        self.assertIs(self.event(grant).outcome, Outcome.DENIED)

    def test_source_port_requires_the_consumed_grant_and_same_request_context(self):
        grant, row, context = self.seed()
        flow = assemble_reveal(components=self.components)
        with DjangoUnitOfWork():
            self.assertIs(flow.sources.read(grant, context).code, ReasonCode.AUTHORIZATION_DENIED)
            consumed = flow.repository.consume(grant, context, grant.object_version,
                                              datetime.now(timezone.utc))
            self.assertIsInstance(consumed, RevealGrant)
            self.assertIsInstance(flow.sources.read(consumed, context), RevealSource)
            self.assertIs(flow.sources.read(grant, context).code, ReasonCode.AUTHORIZATION_DENIED)
            self.assertIs(flow.sources.read(consumed, replace(context, trace_id='trace/another')).code,
                          ReasonCode.AUTHORIZATION_DENIED)
        self.assertIs(flow.sources.read(consumed, context).code, ReasonCode.AUTHORIZATION_DENIED)
        row.refresh_from_db()
        self.assertEqual(row.state, 'approved')
        self.assertIsNone(row.consumed_at)

    def test_legal_sources_use_task_or_snapshot_owner_not_report_generator(self):
        CTFUser.objects.filter(pk=self.requester.pk).update(role='teacher')
        self.requester.refresh_from_db()
        task = LegalAnalysisTask.objects.create(title='合成审查', created_by=self.requester, input_text=MARKER)
        report = LegalReport.objects.create(title='合成报告', task=task, generated_by=self.admin, content=MARKER)
        CTFUser.objects.filter(pk=self.requester.pk).update(role='student')
        self.requester.refresh_from_db()
        grant, row, context = self.seed(target=task, field=RevealField.EVIDENCE,
                                       field_ref='legal.legalanalysistask/input_text')
        with patch.object(self.components['crypto'], 'open') as opened:
            result = self.reveal(grant, context)
            opened.assert_not_called()
        self.assertIs(result.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertIs(self.event(grant).outcome, Outcome.DENIED)
        CTFUser.objects.filter(pk=self.requester.pk).update(role='teacher')
        self.requester.refresh_from_db()
        for target, category, reference in ((task, RevealField.EVIDENCE, 'legal.legalanalysistask/input_text'),
                                          (report, RevealField.REPORT, 'legal.legalreport/content')):
            grant, row, context = self.seed(target=target, field=category, field_ref=reference)
            result = self.reveal(grant, context)
            self.assertEqual(result.tree.to_value()[reference], MARKER)
            self.assertIs(self.event(grant).outcome, Outcome.SUCCEEDED)
        grant, row, context = self.seed(target=report, field=RevealField.REPORT, field_ref='legal.legalreport/content')
        snapshot = LegalFactSnapshot.objects.create(source_kind='hybrid', scope={'subject_user_id': self.admin.pk},
            automated_facts={}, preview_hash='a' * 64, snapshot_hash='b' * 64,
            analysis_task=task, confirmed_by=self.requester)
        result = self.reveal(grant, context)
        self.assertIs(result.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertIs(self.event(grant).outcome, Outcome.DENIED)
        snapshot.scope = {}
        snapshot.save(update_fields=['scope'])
        grant, row, context = self.seed(target=task, field=RevealField.EVIDENCE,
                                       field_ref='legal.legalanalysistask/input_text')
        self.assertIs(self.reveal(grant, context).code, ReasonCode.AUTHORIZATION_DENIED)
