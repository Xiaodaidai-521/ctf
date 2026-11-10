"""Read-only source identity lookup and its handoff to the existing request flow."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.db import DatabaseError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from audit.models import AuditEvent, AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend import security_bootstrap as bootstrap
from data_security.adapters.django import reveal_api
from data_security.adapters.persistence import fields as field_module
from data_security.adapters.persistence.models import RevealRequest
from data_security.contracts import BASELINE_LIMITS, Outlet, PolicySnapshot, Purpose, Role, content_hash
from data_security.tests.phase4_fixtures import field_configuration
from learning_paths.models import LearningPath
from legal.models import LegalAnalysisTask, LegalReport
from users.models import CTFUser, CourseDataGrant

BASE = '/api/data-security/reveal-source/'
REQUESTS = '/api/data-security/reveal-requests/'
MARKER = 'source-lookup-private@example.invalid'


class RevealSourcePostgresTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires the owned synthetic PostgreSQL')
        files = field_configuration()
        self.path, self.config, _, binding = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        policy_path = Path(self.config['policy_file'])
        policy = PolicySnapshot.from_json(policy_path.read_bytes())
        rules = policy.rules + tuple(replace(rule, role=role, purpose=Purpose.INVESTIGATION)
            for rule in policy.rules if rule.outlet is Outlet.API
            for role in (Role.STUDENT, Role.TEACHER, Role.ADMIN))
        values = dict(policy.content(), version='phase7-source-lookup-synthetic.v1', rules=rules)
        digest = content_hash(values)
        policy = PolicySnapshot(**values, status=policy.status, content_hash=digest,
            approval=replace(policy.approval, approval_ref='approval/phase7-source-lookup', content_hash=digest))
        policy_path.write_text(json.dumps(policy.to_wire()))
        self.config['policy_binding'] = replace(binding, protection_version=policy.version,
                                                protection_hash=digest).to_wire()
        checkpoints = self.path.parent / 'lookup-checkpoints'
        checkpoints.mkdir(mode=0o700)
        self.config['audit_chain'] = {
            'chain_version': 'ds.audit.v2', 'project_ref': 'phase7/source-lookup-synthetic',
            'object_uuid': '00000000-0000-4000-8000-000000000019', 'object_version': 'v1',
            'authorization_ref': 'authorization/phase7-source-lookup', 'retained_keys': [],
            'checkpoint_root': str(checkpoints), 'checkpoint_ref': None,
        }
        self.config['reveal_requests'] = {'enabled': True}
        self.path.write_text(json.dumps(self.config))
        self.components = bootstrap.assemble(config_path=self.path)
        previous = field_module._adapter
        self.addCleanup(field_module.bind_field_storage, previous)
        field_module.bind_field_storage(self.components['fields'])
        for name in ('_binding', '_source_reader'):
            binding_patch = patch.object(reveal_api, name, None)
            binding_patch.start()
            self.addCleanup(binding_patch.stop)
        self.reader = self.components['reveal_source']
        self.repository = self.reader.__self__
        reveal_api.bind_reveal_api(factory=self.components['reveal_requests'], clock=self.components['clock'],
            identifier=lambda: uuid4().hex, limits=BASELINE_LIMITS, source_reader=self.reader)
        self.client = APIClient()
        self.owner = CTFUser.objects.create_user(username='lookup-owner', email=MARKER, role='student')
        self.reviewer = CTFUser.objects.create_user(username='lookup-reviewer', role='teacher', is_staff=True)
        self.admin = CTFUser.objects.create_user(username='lookup-admin', role='admin', is_staff=True, is_superuser=True)
        self.course = LearningPath.objects.create(title='合成定位课程', slug='source-lookup-synthetic',
                                                   description='合成资料', difficulty='AP')
        self.access = CourseDataGrant.objects.create(actor=self.reviewer, student=self.owner, course=self.course,
            granted_by=self.reviewer, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    def lookup(self, actor, **changes):
        self.client.force_authenticate(user=actor)
        query = dict(source_id=self.owner.pk, field='email', field_ref='users.ctfuser/email')
        query.update(changes)
        response = self.client.get(BASE, query)
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        self.assertEqual(response['Pragma'], 'no-cache')
        return response

    def request_body(self, metadata):
        return dict(metadata, purpose='investigation', reason='核对合成材料 ' + MARKER, course_id=self.course.pk)

    def test_owner_lookup_returns_only_current_server_identity(self):
        response = self.lookup(self.owner)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'object_ref': str(self.owner.security_uuid),
            'object_version': 'v' + str(self.owner.security_revision), 'fields': [['email', 'users.ctfuser/email']]})
        self.assertNotIn(MARKER, response.content.decode())
        self.assertEqual(RevealRequest.objects.count(), 0)

    def test_role_alone_and_missing_rows_have_the_same_denial(self):
        for actor, source_id in ((self.admin, self.owner.pk), (self.admin, 2**62),
                                 (self.reviewer, self.owner.pk), (self.reviewer, 2**62)):
            with self.subTest(role=actor.role, exists=source_id == self.owner.pk):
                response = self.lookup(actor, source_id=source_id)
                self.assertEqual((response.status_code, response.data), (403, {'code': 'AUTHORIZATION_DENIED'}))
        with patch.object(reveal_api, '_source_reader', wraps=self.reader) as reader:
            self.assertEqual(self.lookup(None).status_code, 403)
            reader.assert_not_called()

    def test_current_course_permission_is_required_and_revocation_is_observed(self):
        self.assertEqual(self.lookup(self.reviewer, course_id=self.course.pk).status_code, 200)
        CourseDataGrant.objects.filter(pk=self.access.pk).update(active=False)
        self.assertEqual(self.lookup(self.reviewer, course_id=self.course.pk).status_code, 403)
        CourseDataGrant.objects.filter(pk=self.access.pk).update(active=True,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        self.assertEqual(self.lookup(self.reviewer, course_id=self.course.pk).status_code, 403)

    def test_inactive_and_changed_roles_are_reloaded_from_the_database(self):
        CTFUser.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assertEqual(self.lookup(self.owner).status_code, 403)
        CTFUser.objects.filter(pk=self.owner.pk).update(is_active=True, role='teacher')
        self.assertEqual(self.lookup(self.owner).status_code, 403)

    def test_legal_reviewer_and_actual_task_owner_rules_are_preserved(self):
        task = LegalAnalysisTask.objects.create(created_by=self.owner, input_text=MARKER)
        report = LegalReport.objects.create(task=task, generated_by=self.admin, content=json.dumps({'evidence': MARKER}))
        for target, category, reference in ((task, 'evidence', 'legal.legalanalysistask/input_text'),
                                             (report, 'report', 'legal.legalreport/content')):
            with self.subTest(category=category):
                query = dict(source_id=target.pk, field=category, field_ref=reference, course_id=self.course.pk)
                allowed = self.lookup(self.reviewer, **query)
                self.assertEqual(allowed.status_code, 200)
                self.assertEqual(allowed.data, {'object_ref': str(target.security_uuid),
                    'object_version': 'v' + str(target.security_revision), 'fields': [[category, reference]]})
                self.assertEqual(self.lookup(self.owner, **query).status_code, 403)
                self.assertEqual(self.lookup(self.admin, **query).status_code, 403)
                self.assertNotIn(MARKER, allowed.content.decode())

    def test_success_selects_metadata_without_decryption_signing_or_writes(self):
        models = (CTFUser, RevealRequest, AuditEvent, AuthenticatedAuditEntry, SecurityAuditRecord)
        before = [model.objects.count() for model in models]
        with patch.object(self.components['crypto'], 'open') as opened, \
                patch.object(self.components['crypto'], 'authenticate') as signed, \
                patch.object(self.repository, 'source') as source, \
                CaptureQueriesContext(connection) as captured:
            response = self.lookup(self.owner)
        self.assertEqual(response.status_code, 200)
        opened.assert_not_called()
        signed.assert_not_called()
        source.assert_not_called()
        self.assertEqual([model.objects.count() for model in models], before)
        self.assertTrue(captured.captured_queries)
        for query in captured.captured_queries:
            sql = query['sql']
            self.assertTrue(sql.lstrip().upper().startswith('SELECT'))
            for column in ('"security_envelopes"', '"email"', '"password"', '"input_text"', '"content"'):
                self.assertNotIn(column, sql.split(' FROM ', 1)[0])

    def test_http_query_is_closed_single_valued_and_bounded(self):
        self.client.force_authenticate(user=self.owner)
        normal = {'source_id': self.owner.pk, 'field': 'email', 'field_ref': 'users.ctfuser/email'}
        invalid = [{}, {**normal, 'role': 'admin'}, {**normal, 'object_version': 'v1'},
            {**normal, 'approved': 'true'}, {**normal, 'source_id': 0}, {**normal, 'source_id': -1},
            {**normal, 'source_id': 2**63}, {**normal, 'source_id': 'not-a-number'},
            {**normal, 'source_id': [self.owner.pk, self.admin.pk]}, {**normal, 'field': ['email', 'report']},
            {**normal, 'course_id': 0}, {**normal, 'course_id': 100001}, {**normal, 'field': 'password'},
            {**normal, 'field_ref': '../../password'}]
        with patch.object(reveal_api, '_source_reader', wraps=self.reader) as reader:
            for query in invalid:
                with self.subTest(query_keys=sorted(query)):
                    response = self.client.get(BASE, query)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response['Cache-Control'], 'no-store, private')
                    self.assertNotIn('not-a-number', response.content.decode())
            response = self.client.post(BASE, normal, format='json')
            self.assertEqual(response.status_code, 405)
            self.assertEqual(response['Cache-Control'], 'no-store, private')
            reader.assert_not_called()

    def test_field_category_and_reference_cannot_select_another_domain(self):
        for category, reference in (('report', 'users.ctfuser/email'), ('email', 'users.ctfuser/password'),
                                   ('email', 'ai_assistant.aimessage/content'),
                                   ('evidence', 'legal.legalfactsnapshot/manual_notes')):
            with self.subTest(category=category, reference=reference):
                response = self.lookup(self.owner, field=category, field_ref=reference)
                self.assertEqual((response.status_code, response.data), (400, {'code': 'UNSUPPORTED_SCOPE'}))

    def test_disabled_field_storage_and_legacy_rows_are_not_available_sources(self):
        with patch.object(field_module, '_adapter', None):
            self.assertEqual(self.lookup(self.owner).data, {'code': 'SOURCE_NOT_APPROVED'})
            legacy = CTFUser.objects.create_user(username='lookup-legacy', role='student')
        response = self.lookup(legacy, source_id=legacy.pk)
        self.assertEqual((response.status_code, response.data), (503, {'code': 'SOURCE_NOT_APPROVED'}))

    def test_unbound_capability_and_database_errors_do_not_return_identity(self):
        with patch.object(reveal_api, '_source_reader', None):
            response = self.lookup(self.owner)
            self.assertEqual((response.status_code, response.data),
                             (503, {'code': 'POLICY_NOT_APPROVED', 'state': 'disabled'}))
        with patch.object(self.repository, '_current_actor', side_effect=DatabaseError(MARKER)):
            response = self.lookup(self.owner)
            self.assertEqual((response.status_code, response.data), (503, {'code': 'AUDIT_UNAVAILABLE'}))
            self.assertNotIn(MARKER, response.content.decode())
        self.config['reveal_requests']['enabled'] = False
        self.path.write_text(json.dumps(self.config))
        disabled = bootstrap.assemble(config_path=self.path)
        self.assertIsNone(disabled['reveal_source'])
        self.assertIsNone(disabled['reveal_requests'])
        reveal_api.bind_reveal_api(source_reader=self.reader)
        self.assertIsNone(reveal_api._binding)
        self.assertIsNone(reveal_api._source_reader)

    def test_lookup_metadata_can_submit_but_never_authorizes_a_stale_version(self):
        original = self.lookup(self.owner)
        self.assertEqual(original.status_code, 200)
        self.owner.nickname = '合成资料更新'
        self.owner.save(update_fields=['nickname'])
        with patch.object(self.components['crypto'], 'open') as opened:
            stale = self.client.post(REQUESTS, self.request_body(original.data), format='json')
            self.assertEqual((stale.status_code, stale.data), (403, {'code': 'AUTHORIZATION_DENIED'}))
            self.assertEqual(RevealRequest.objects.count(), 0)
            fresh = self.lookup(self.owner)
            self.assertNotEqual(fresh.data['object_version'], original.data['object_version'])
            submitted = self.client.post(REQUESTS, self.request_body(fresh.data), format='json')
            self.assertEqual(submitted.status_code, 201)
            self.assertEqual(submitted.data['state'], 'pending')
            row = RevealRequest.objects.get(request_ref=submitted.data['id'])
            self.assertIsNone(row.grant_document)
            self.assertNotIn(MARKER, row.reason)
            opened.assert_not_called()

    def test_lookup_metadata_does_not_survive_owner_permission_revocation(self):
        response = self.lookup(self.reviewer, course_id=self.course.pk)
        self.assertEqual(response.status_code, 200)
        CourseDataGrant.objects.filter(pk=self.access.pk).update(active=False)
        denied = self.client.post(REQUESTS, self.request_body(response.data), format='json')
        self.assertEqual((denied.status_code, denied.data), (403, {'code': 'AUTHORIZATION_DENIED'}))
        self.assertEqual(RevealRequest.objects.count(), 0)
