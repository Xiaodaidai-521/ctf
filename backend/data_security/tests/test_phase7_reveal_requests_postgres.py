"""New application/approval/HTTP checks on synthetic, isolated PostgreSQL.

Unlike the read-only group, approvals are issued by M4 through the real M6 and
v2 audit chain. Existing TestCase classes are not imported into this module.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from rest_framework.settings import api_settings
from rest_framework.test import APIClient
from rest_framework.views import APIView

from audit.models import AuditEvent, AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend import security_bootstrap as bootstrap
from data_security.adapters.django import policy_api, reveal_api
from data_security.adapters.persistence import fields as field_module
from data_security.adapters.persistence.models import RevealRequest
from data_security.contracts import (
    BASELINE_LIMITS, AuditReceipt, ContractViolation, Durability, Environment, EventKind, Outcome, Outlet,
    PolicySnapshot, ProtectionContext, ProtectionError, Purpose, ReasonCode, RevealField, RevealGrant,
    RevealRequestRecord, Role, SecurityEventV2, content_hash,
)
from data_security.tests.phase4_fixtures import field_configuration
from learning_paths.models import LearningPath
from legal.models import LegalAnalysisTask, LegalReport
from users.models import CTFUser, CourseDataGrant

MARKER = 'reveal-request-private@example.invalid'
ADDRESS = '192.0.2.17'
CARD = '4111111111111111'
BASE = '/api/data-security/reveal-requests/'


class RevealRequestPostgresTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL, never SQLite')
        files = field_configuration()
        self.path, self.config, _, binding = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        policy_path = Path(self.config['policy_file'])
        policy = PolicySnapshot.from_json(policy_path.read_bytes())
        rules = policy.rules + tuple(replace(rule, role=role, purpose=Purpose.INVESTIGATION)
            for rule in policy.rules if rule.outlet is Outlet.API
            for role in (Role.STUDENT, Role.TEACHER, Role.ADMIN))
        values = dict(policy.content(), version='phase7-reveal-request-synthetic.v1', rules=rules)
        digest = content_hash(values)
        policy = PolicySnapshot(**values, status=policy.status, content_hash=digest,
            approval=replace(policy.approval, approval_ref='approval/phase7-reveal-request-synthetic',
                             content_hash=digest))
        policy_path.write_text(json.dumps(policy.to_wire()))
        self.config['policy_binding'] = replace(binding, protection_version=policy.version,
                                                protection_hash=digest).to_wire()
        checkpoints = self.path.parent / 'reveal-request-checkpoints'
        checkpoints.mkdir(mode=0o700)
        self.config['audit_chain'] = {
            'chain_version': 'ds.audit.v2', 'project_ref': 'phase7/reveal-request-synthetic',
            'object_uuid': '00000000-0000-4000-8000-000000000017', 'object_version': 'v1',
            'authorization_ref': 'authorization/phase7-reveal-request-synthetic', 'retained_keys': [],
            'checkpoint_root': str(checkpoints), 'checkpoint_ref': None,
        }
        self.config['reveal_requests'] = {'enabled': True}
        self.path.write_text(json.dumps(self.config))
        self.components = bootstrap.assemble(config_path=self.path)
        previous = field_module._adapter
        self.addCleanup(field_module.bind_field_storage, previous)
        field_module.bind_field_storage(self.components['fields'])
        for module in (policy_api, reveal_api):
            binding = patch.object(module, '_binding', None)
            binding.start()
            self.addCleanup(binding.stop)
        reveal_api.bind_reveal_api(factory=self.components['reveal_requests'],
            clock=self.components['clock'], identifier=lambda: uuid4().hex,
            limits=BASELINE_LIMITS)
        self.client = APIClient()
        self.requester = CTFUser.objects.create_user(username='reveal-request-owner', email=MARKER, role='student')
        self.reviewer = CTFUser.objects.create_user(username='reveal-request-reviewer', role='teacher', is_staff=True)
        self.admin = CTFUser.objects.create_user(username='reveal-request-admin', role='admin',
                                                is_staff=True, is_superuser=True)
        self.course = LearningPath.objects.create(title='合成申请课程', slug='reveal-request-synthetic',
                                                   description='合成课程', difficulty='AP')
        self.access = CourseDataGrant.objects.create(actor=self.reviewer, student=self.requester,
            course=self.course, granted_by=self.reviewer, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    def body(self, target=None, **changes):
        target = self.requester if target is None else target
        return dict({'object_ref': str(target.security_uuid), 'object_version': 'v' + str(target.security_revision),
            'fields': [[RevealField.EMAIL.value, 'users.ctfuser/email']], 'course_id': self.course.pk,
            'purpose': 'investigation', 'reason': '核对合成资料 ' + MARKER + ' ' + ADDRESS + ' ' + CARD}, **changes)

    def post(self, user, *, request_ref=None, action=None, data=None):
        self.client.force_authenticate(user=user)
        url = BASE if request_ref is None else BASE + request_ref + '/' + action + '/'
        response = self.client.post(url, {} if data is None else data, format='json')
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        self.assertEqual(response['Pragma'], 'no-cache')
        return response

    def submit(self, user=None, *, target=None, **changes):
        user = self.requester if user is None else user
        response = self.post(user, data=self.body(target, **changes))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['state'], 'pending')
        return RevealRequest.objects.get(request_ref=response.data['id'])

    def approve(self, row, user=None):
        user = self.reviewer if user is None else user
        response = self.post(user, request_ref=row.request_ref, action='approve')
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.state, 'approved')
        return response

    def events(self, reference, *, action=None):
        rows = SecurityAuditRecord.objects.filter(event__correlation_ref=reference).order_by('pk')
        result = []
        for row in rows:
            event = SecurityEventV2.from_wire(row.event)
            if action is not None and event.algorithm_versions != ('ds.reveal-request.v1', action):
                continue
            self.assertEqual(self.components['audit'].sink.read_authenticated(event.event_id), event)
            self.assertNotIn(MARKER, json.dumps(event.to_wire()))
            result.append(event)
        return result

    def test_missing_investigation_policy_rejects_before_request_storage(self):
        policy_path = Path(self.config['policy_file'])
        policy = PolicySnapshot.from_json(policy_path.read_bytes())
        values = dict(policy.content(), version='phase7-reveal-request-missing.v1',
                      rules=tuple(rule for rule in policy.rules if rule.purpose is not Purpose.INVESTIGATION))
        digest = content_hash(values)
        policy = PolicySnapshot(**values, status=policy.status, content_hash=digest,
            approval=replace(policy.approval, approval_ref='approval/phase7-reveal-request-missing',
                             content_hash=digest))
        policy_path.write_text(json.dumps(policy.to_wire()))
        self.config['policy_binding'] = replace(self.components['binding'],
            protection_version=policy.version, protection_hash=digest).to_wire()
        self.path.write_text(json.dumps(self.config))
        components = bootstrap.assemble(config_path=self.path)
        flow = components['reveal_requests']()
        with patch.object(flow.requests, 'submit') as submitted, patch.object(reveal_api, '_binding',
                (lambda: flow, components['clock'], lambda: uuid4().hex, BASELINE_LIMITS)):
            for user in (self.requester, self.reviewer, self.admin):
                with self.subTest(role=user.role):
                    response = self.post(user, data=self.body())
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.data['code'], 'POLICY_NOT_APPROVED')
                    self.assertNotIn(MARKER, json.dumps(response.data))
            submitted.assert_not_called()
        self.assertEqual(RevealRequest.objects.count(), 0)
        self.assertFalse(SecurityAuditRecord.objects.filter(
            event__kind=EventKind.AUTHORIZATION.value, event__outcome=Outcome.SUCCEEDED.value).exists())

    def test_request_reason_is_protected_before_storage_and_listing(self):
        with patch.object(self.components['crypto'], 'open') as opened:
            row = self.submit()
            opened.assert_not_called()
        for marker in (MARKER, ADDRESS, CARD):
            self.assertNotIn(marker, row.reason)
        self.assertIn('核对合成资料', row.reason)
        self.assertEqual(row.fields, [[RevealField.EMAIL.value, 'users.ctfuser/email']])
        self.assertIsNone(row.grant_document)
        self.assertIsNone(row.approved_by_id)
        event, = self.events(row.request_ref, action='request')
        self.assertIs(event.kind, EventKind.AUTHORIZATION)
        self.assertIs(event.outcome, Outcome.SUCCEEDED)
        self.assertEqual(event.counts, (('processed', 1),))
        self.assertEqual(len(event.evidence_hashes), 1)
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.get(BASE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        self.assertEqual(response.data['items'][0]['reason'], row.reason)
        self.assertNotIn(MARKER, json.dumps(response.data))
        self.assertNotIn('grant_document', response.data['items'][0])

    def test_full_http_flow_requires_server_approval_then_one_authenticated_read(self):
        self.requester.bio = '合成全局版本更新'
        self.requester.save(update_fields=['bio'])
        original = deepcopy(self.requester.security_envelopes)
        row = self.submit()
        self.approve(row)
        self.assertEqual(row.approved_by_id, self.reviewer.pk)
        self.assertEqual(row.decided_by_ref, 'user/' + str(self.reviewer.pk))
        self.assertEqual(row.grant_document['subject_ref'], 'user/' + str(self.requester.pk))
        self.assertEqual(row.grant_document['object_version'], 'v2')
        expires = datetime.fromisoformat(row.grant_document['expires_at'].replace('Z', '+00:00'))
        issued = datetime.fromisoformat(row.grant_document['issued_at'].replace('Z', '+00:00'))
        self.assertEqual((expires - issued).total_seconds(), 900)
        approved, = self.events(row.request_ref, action='approve')
        self.assertEqual(approved.event_id, row.decision_event_ref)
        self.assertEqual(approved.actor_ref, row.decided_by_ref)
        flow = self.components['reveal_requests']()
        self.assertIs(flow.repository, flow.sources)
        with transaction.atomic():
            record = flow.requests._record_row(RevealRequest.objects.get(pk=row.pk))
        self.assertEqual(approved.evidence_hashes, (('report', content_hash(record.authorization_content())),))
        receipt_ids, opened_contexts = [], []
        real_open, real_record = self.components['crypto'].open, self.components['audit'].record

        def open_field(envelope, context, key):
            self.assertTrue(connection.in_atomic_block)
            self.assertEqual(RevealRequest.objects.get(pk=row.pk).state, 'consumed')
            opened_contexts.append(context)
            return real_open(envelope, context, key)

        def record_event(event, durability):
            receipt = real_record(event, durability)
            if event.kind is EventKind.REVEAL:
                self.assertTrue(connection.in_atomic_block)
                self.assertEqual(RevealRequest.objects.get(pk=row.pk).state, 'consumed')
                self.assertIs(receipt.durability, Durability.LEDGER_CONFIRMED)
                self.assertEqual(receipt.chain_version, 'ds.audit.v2')
                receipt_ids.append(receipt.event_id)
            return receipt

        with patch.object(self.components['crypto'], 'open', side_effect=open_field), \
                patch.object(self.components['audit'], 'record', side_effect=record_event):
            response = self.post(self.requester, request_ref=row.request_ref, action='read')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'originals': {'users.ctfuser/email': MARKER}})
        self.assertFalse(connection.in_atomic_block)
        self.assertEqual(len(opened_contexts), 1)
        self.assertEqual(opened_contexts[0].object_version, 'v1')
        self.assertEqual(opened_contexts[0].authorization_ref, 'authorization/phase4-storage')
        self.assertEqual(CTFUser.objects.get(pk=self.requester.pk).security_envelopes, original)
        self.assertEqual(CTFUser.objects.get(pk=self.requester.pk).email, '')
        success, = self.events(row.grant_id)
        self.assertEqual(receipt_ids, [success.event_id])
        self.assertIs(success.outcome, Outcome.SUCCEEDED)
        with patch.object(self.components['crypto'], 'open') as opened:
            replay = self.post(self.requester, request_ref=row.request_ref, action='read')
            opened.assert_not_called()
        self.assertEqual(replay.status_code, 403)
        self.assertNotIn(MARKER, json.dumps(replay.data))
        denied, = [event for event in self.events(row.request_ref) if event.kind is EventKind.REVEAL]
        self.assertIs(denied.outcome, Outcome.DENIED)

    def test_self_decisions_unscoped_admin_and_non_requester_reads_have_no_exemption(self):
        row = self.submit()
        for user, action in ((self.requester, 'approve'), (self.requester, 'reject'),
                             (self.admin, 'approve'), (self.admin, 'reject')):
            with self.subTest(user=user.role, action=action):
                response = self.post(user, request_ref=row.request_ref, action=action)
                self.assertEqual(response.status_code, 403)
                row.refresh_from_db()
                self.assertEqual(row.state, 'pending')
                self.assertIsNone(row.grant_id)
        self.approve(row)
        for user in (self.reviewer, self.admin):
            with self.subTest(user=user.role), patch.object(self.components['crypto'], 'open') as opened:
                response = self.post(user, request_ref=row.request_ref, action='read')
                opened.assert_not_called()
                self.assertEqual(response.status_code, 403)
        self.assertTrue(all(event.outcome is Outcome.DENIED for event in
                            self.events(row.request_ref) if event.reason is not None))

    def test_approval_rechecks_both_current_owners_roles_version_and_read_key(self):
        cases = ('requester-inactive', 'reviewer-inactive', 'course-revoked', 'course-expired',
                 'reviewer-student', 'version-changed', 'read-key-missing')
        for case in cases:
            with self.subTest(case=case):
                row = self.submit()
                if case in ('requester-inactive', 'reviewer-inactive'):
                    user = self.requester if case == 'requester-inactive' else self.reviewer
                    CTFUser.objects.filter(pk=user.pk).update(is_active=False)
                elif case.startswith('course-'):
                    CourseDataGrant.objects.filter(pk=self.access.pk).update(active=case != 'course-revoked',
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=-1 if case == 'course-expired' else 1))
                elif case == 'reviewer-student':
                    CTFUser.objects.filter(pk=self.reviewer.pk).update(role='student')
                elif case == 'version-changed':
                    self.requester.bio = '合成版本 ' + uuid4().hex
                    self.requester.save(update_fields=['bio'])
                else:
                    saved_keys = self.components['fields'].read_keys
                    self.components['fields'].read_keys = {}
                self.reviewer.refresh_from_db()
                with patch.object(self.components['crypto'], 'open') as opened:
                    response = self.post(self.reviewer, request_ref=row.request_ref, action='approve')
                    opened.assert_not_called()
                self.assertEqual(response.status_code, 503 if case == 'read-key-missing' else 403)
                row.refresh_from_db()
                self.assertEqual(row.state, 'pending')
                self.assertIsNone(row.decision_event_ref)
                self.assertIsNone(row.grant_id)
                CTFUser.objects.filter(pk__in=(self.requester.pk, self.reviewer.pk)).update(is_active=True)
                CTFUser.objects.filter(pk=self.reviewer.pk).update(role='teacher')
                CourseDataGrant.objects.filter(pk=self.access.pk).update(active=True,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
                if case == 'read-key-missing':
                    self.components['fields'].read_keys = saved_keys
                self.requester.refresh_from_db()
                self.reviewer.refresh_from_db()

    def test_rejection_and_authorized_revocation_do_not_need_an_unchanged_ciphertext(self):
        row = self.submit()
        saved_keys = self.components['fields'].read_keys
        self.components['fields'].read_keys = {}
        response = self.post(self.reviewer, request_ref=row.request_ref, action='reject')
        self.components['fields'].read_keys = saved_keys
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.state, 'rejected')
        self.assertIsNone(row.grant_id)
        rejected, = self.events(row.request_ref, action='reject')
        self.assertEqual(rejected.event_id, row.decision_event_ref)
        for user in (self.requester, self.reviewer):
            with self.subTest(revoker=user.role):
                row = self.submit()
                self.approve(row)
                unscoped = self.post(self.admin, request_ref=row.request_ref, action='revoke')
                self.assertEqual(unscoped.status_code, 403)
                self.requester.bio = '合成后续版本 ' + uuid4().hex
                self.requester.save(update_fields=['bio'])
                response = self.post(user, request_ref=row.request_ref, action='revoke')
                self.assertEqual(response.status_code, 200)
                row.refresh_from_db()
                self.assertEqual(row.state, 'revoked')
                self.assertEqual(row.decided_by_ref, 'user/' + str(user.pk))
                self.assertIsNotNone(row.revoked_at)
                revoked, = [event for event in self.events(row.request_ref, action='revoke')
                            if event.outcome is Outcome.SUCCEEDED]
                self.assertEqual(revoked.event_id, row.decision_event_ref)
                with patch.object(self.components['crypto'], 'open') as opened:
                    read = self.post(self.requester, request_ref=row.request_ref, action='read')
                    opened.assert_not_called()
                self.assertEqual(read.status_code, 403)

    def test_list_uses_current_object_scope_and_visible_row_pagination(self):
        first, second = self.submit(), self.submit()
        unrelated = CTFUser.objects.create_user(username='reveal-request-unrelated', role='student')
        hidden = self.submit(user=unrelated, target=unrelated)
        for user, expected in ((self.requester, [first.request_ref, second.request_ref]),
                               (self.reviewer, [first.request_ref, second.request_ref]), (self.admin, [])):
            with self.subTest(user=user.role):
                self.client.force_authenticate(user=user)
                response = self.client.get(BASE)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([item['id'] for item in response.data['items']], expected)
                self.assertNotIn(hidden.request_ref, json.dumps(response.data))
                self.assertNotIn(MARKER, json.dumps(response.data))
        self.client.force_authenticate(user=self.requester)
        page = self.client.get(BASE, {'offset': 1, 'limit': 1})
        self.assertEqual([item['id'] for item in page.data['items']], [second.request_ref])
        self.assertEqual(page.data['state'], 'enabled-unverified')
        for query in ({'offset': -1}, {'limit': 0}, {'limit': 101}, {'role': 'admin'}):
            with self.subTest(query=query):
                response = self.client.get(BASE, query)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response['Cache-Control'], 'no-store, private')
        CourseDataGrant.objects.filter(pk=self.access.pk).update(active=False)
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.get(BASE)
        self.assertEqual(response.data['items'], [])

    def test_client_roles_approvals_grants_expiry_and_scope_replacements_are_rejected(self):
        for name, value in (('role', 'admin'), ('requested_by', 'user/1'), ('approval', {}),
                            ('grant', {}), ('expires_at', '2099-01-01T00:00:00Z'),
                            ('authorization_ref', 'authorization/client')):
            with self.subTest(name=name):
                response = self.post(self.requester, data=self.body(**{name: value}))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data['code'], 'UNKNOWN_FIELD')
        self.assertEqual(RevealRequest.objects.count(), 0)
        for body, status in (
            (self.body(purpose='analysis'), 403),
            (self.body(object_ref=str(uuid4())), 403),
            (self.body(fields=[[RevealField.EMAIL.value, 'users.ctfuser/password']]), 400),
            (self.body(fields=[[RevealField.EMAIL.value, 'keys/data']]), 400),
            (self.body(reason='x' * (BASELINE_LIMITS.max_text_chars + 1)), 400),
            (self.body(fields=[]), 400),
        ):
            with self.subTest(status=status), patch.object(self.components['crypto'], 'open') as opened:
                response = self.post(self.requester, data=body)
                opened.assert_not_called()
                self.assertEqual(response.status_code, status)
                self.assertNotIn(MARKER, json.dumps(response.data))
        self.assertEqual(RevealRequest.objects.count(), 0)
        row = self.submit()
        for action in ('approve', 'reject', 'revoke', 'read'):
            with self.subTest(action=action):
                response = self.post(self.reviewer, request_ref=row.request_ref, action=action,
                                     data={'fields': [['email', 'users.ctfuser/password']], 'role': 'admin'})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data['code'], 'UNKNOWN_FIELD')
        row.refresh_from_db()
        self.assertEqual(row.state, 'pending')

    def test_disabled_authentication_parse_media_and_method_responses_are_no_store(self):
        self.client.force_authenticate(user=None)
        anonymous = self.client.get(BASE)
        self.assertIn(anonymous.status_code, (401, 403))
        self.assertEqual(anonymous['Cache-Control'], 'no-store, private')
        self.client.force_authenticate(user=self.requester)
        for method, url, data, content_type, status in (
            ('post', BASE, '{"reason":' + MARKER, 'application/json', 400),
            ('post', BASE, MARKER, 'text/plain', 415),
            ('get', BASE + 'synthetic/read/', None, None, 405),
            ('delete', BASE, None, None, 405),
        ):
            with self.subTest(status=status):
                kwargs = {} if content_type is None else {'data': data, 'content_type': content_type}
                response = getattr(self.client, method)(url, **kwargs)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response['Cache-Control'], 'no-store, private')
                self.assertEqual(response['Pragma'], 'no-cache')
                self.assertNotIn(MARKER, response.content.decode())
        reveal_api.bind_reveal_api()
        for response in (self.client.get(BASE), self.client.post(BASE, {}, format='json'),
                         self.client.post(BASE + 'synthetic/read/', {}, format='json')):
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.data['state'], 'disabled')
            self.assertEqual(response['Cache-Control'], 'no-store, private')

    def test_request_and_all_decision_state_writes_roll_back_with_their_success_event(self):
        real_record = self.components['audit'].record
        for action in ('request', 'approve', 'reject', 'revoke'):
            with self.subTest(action=action):
                row = None if action == 'request' else self.submit()
                if action == 'revoke':
                    self.approve(row)
                before_rows = RevealRequest.objects.count()
                before_entries = AuthenticatedAuditEntry.objects.count()
                before_entry_ids = list(AuthenticatedAuditEntry.objects.values_list('pk', flat=True))
                before_http_errors = AuditEvent.objects.filter(summary='HTTP_SERVER_ERROR').count()

                def record_event(event, durability):
                    receipt = real_record(event, durability)
                    if event.algorithm_versions == ('ds.reveal-request.v1', action) and event.outcome is Outcome.SUCCEEDED:
                        self.assertTrue(connection.in_atomic_block)
                        return None
                    return receipt

                with patch.object(self.components['audit'], 'record', side_effect=record_event):
                    response = self.post(self.requester if action == 'request' else self.reviewer,
                        request_ref=None if row is None else row.request_ref,
                        action=None if row is None else action,
                        data=self.body() if row is None else {})
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.data['code'], 'AUDIT_UNAVAILABLE')
                self.assertEqual(RevealRequest.objects.count(), before_rows)
                if row is not None:
                    row.refresh_from_db()
                    self.assertEqual(row.state, 'approved' if action == 'revoke' else 'pending')
                    self.assertIsNone(row.revoked_at)
                    if action != 'revoke':
                        self.assertIsNone(row.grant_document)
                        self.assertIsNone(row.decision_event_ref)
                    event, = [event for event in self.events(row.request_ref, action=action)
                              if event.outcome is not Outcome.SUCCEEDED]
                    self.assertIs(event.outcome, Outcome.FAILED)
                new_events = AuthenticatedAuditEntry.objects.exclude(pk__in=before_entry_ids).values_list('record__event', flat=True)
                expected = [('protection', 'succeeded', ['replace-v1'])] if action == 'request' else []
                expected += [('authorization', 'failed', ['ds.reveal-request.v1', action]),
                             ('protection', 'succeeded', [])]
                self.assertEqual([(event['kind'], event['outcome'], event['algorithm_versions'])
                                  for event in new_events], expected)
                # The unchanged 5xx middleware protects its audit detail too.
                self.assertEqual(AuditEvent.objects.filter(summary='HTTP_SERVER_ERROR').count(), before_http_errors + 1)
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), before_entries + (3 if action == 'request' else 2))
                successes = SecurityAuditRecord.objects.filter(
                    event__algorithm_versions=['ds.reveal-request.v1', action], event__outcome='succeeded')
                self.assertFalse(successes.exists())

    def test_approval_rejects_weak_v1_wrong_event_and_exception_receipts(self):
        real_record = self.components['audit'].record
        for mode in ('weak', 'v1', 'wrong-event', 'raise'):
            with self.subTest(mode=mode):
                row = self.submit()
                before_entries = AuthenticatedAuditEntry.objects.count()
                before_entry_ids = list(AuthenticatedAuditEntry.objects.values_list('pk', flat=True))
                before_http_errors = AuditEvent.objects.filter(summary='HTTP_SERVER_ERROR').count()

                def record_event(event, durability):
                    receipt = real_record(event, durability)
                    if event.algorithm_versions != ('ds.reveal-request.v1', 'approve') or event.outcome is not Outcome.SUCCEEDED:
                        return receipt
                    if mode == 'raise':
                        raise RuntimeError(MARKER)
                    if mode == 'weak':
                        return AuditReceipt(schema_version=AuditReceipt.SCHEMA, event_id=event.event_id,
                            durability=Durability.DURABLE, stored_at=receipt.stored_at, chain_version=None,
                            entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
                    return replace(receipt, **({'chain_version': 'v1'} if mode == 'v1' else {'event_id': 'b' * 64}))

                with patch.object(self.components['audit'], 'record', side_effect=record_event):
                    response = self.post(self.reviewer, request_ref=row.request_ref, action='approve')
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.data, {'code': 'AUDIT_UNAVAILABLE'})
                row.refresh_from_db()
                self.assertEqual(row.state, 'pending')
                self.assertIsNone(row.grant_document)
                self.assertIsNone(row.decision_event_ref)
                failed, = self.events(row.request_ref, action='approve')
                self.assertIs(failed.outcome, Outcome.FAILED)
                new_events = AuthenticatedAuditEntry.objects.exclude(pk__in=before_entry_ids).values_list('record__event', flat=True)
                self.assertEqual([(event['kind'], event['outcome'], event['algorithm_versions'])
                                  for event in new_events],
                    [('authorization', 'failed', ['ds.reveal-request.v1', 'approve']),
                     ('protection', 'succeeded', [])])
                self.assertEqual(AuditEvent.objects.filter(summary='HTTP_SERVER_ERROR').count(), before_http_errors + 1)
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), before_entries + 2)

    def test_server_grant_metadata_needs_authenticated_approval_not_self_asserted_hashes(self):
        for mode in ('missing-event', 'early-event', 'wrong-event', 'changed-window', 'changed-course', 'changed-request-time'):
            with self.subTest(mode=mode):
                row = self.submit()
                self.approve(row)
                if mode == 'missing-event':
                    row.decision_event_ref = None
                elif mode == 'early-event':
                    row.decision_event_ref = self.events(row.request_ref, action='request')[0].event_id
                elif mode == 'wrong-event':
                    other = self.submit()
                    event, = self.events(other.request_ref, action='request')
                    self.assertGreaterEqual(event.occurred_at, row.decided_at)
                    row.decision_event_ref = event.event_id
                elif mode == 'changed-window':
                    flow = self.components['reveal_requests']()
                    grant = flow.requests._record_row(row).grant
                    values = dict(grant.approved_content(), expires_at=grant.expires_at - timedelta(seconds=60))
                    approval = replace(grant.approval, content_hash=content_hash(values))
                    row.grant_document = RevealGrant(**values, approval=approval, state=grant.state,
                        consumed_at=None, revoked_at=None).to_wire()
                elif mode == 'changed-course':
                    row.course_id = None
                else:
                    row.requested_at -= timedelta(seconds=1)
                row.save(update_fields=['decision_event_ref', 'grant_document', 'course_id', 'requested_at'])
                with patch.object(self.components['crypto'], 'open') as opened:
                    response = self.post(self.requester, request_ref=row.request_ref, action='read')
                    opened.assert_not_called()
                unavailable = mode in ('missing-event', 'early-event')
                self.assertEqual(response.status_code, 503 if unavailable else 403)
                self.assertEqual(response.data, {'code': 'AUDIT_UNAVAILABLE' if unavailable else 'AUTHORIZATION_DENIED'})
                row.refresh_from_db()
                self.assertEqual(row.state, 'approved')
                self.assertIsNone(row.consumed_at)
                denied, = [event for event in self.events(row.request_ref) if event.kind is EventKind.REVEAL]
                self.assertIs(denied.outcome, Outcome.FAILED if unavailable else Outcome.DENIED)

    def test_server_request_read_rechecks_expiry_revocation_version_and_owner(self):
        for mode in ('expired', 'revoked', 'version', 'owner'):
            with self.subTest(mode=mode):
                if mode == 'expired':
                    now = [datetime.now(timezone.utc) - timedelta(minutes=16)]
                    self.components['clock'] = lambda: now[0]
                    reveal_api.bind_reveal_api(factory=self.components['reveal_requests'],
                        clock=self.components['clock'], identifier=lambda: uuid4().hex,
                        limits=BASELINE_LIMITS)
                row = self.submit()
                self.approve(row)
                if mode == 'expired':
                    now[0] += timedelta(seconds=901)
                elif mode == 'revoked':
                    response = self.post(self.reviewer, request_ref=row.request_ref, action='revoke')
                    self.assertEqual(response.status_code, 200)
                elif mode == 'version':
                    self.requester.bio = '合成新版本'
                    self.requester.save(update_fields=['bio'])
                else:
                    CourseDataGrant.objects.filter(pk=self.access.pk).update(active=False)
                with patch.object(self.components['crypto'], 'open') as opened:
                    response = self.post(self.requester, request_ref=row.request_ref, action='read')
                    opened.assert_not_called()
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data['code'], 'AUTHORIZATION_EXPIRED' if mode == 'expired' else 'AUTHORIZATION_DENIED')
                row.refresh_from_db()
                self.assertIsNone(row.consumed_at)
                self.components['clock'] = lambda: datetime.now(timezone.utc)
                reveal_api.bind_reveal_api(factory=self.components['reveal_requests'],
                    clock=self.components['clock'], identifier=lambda: uuid4().hex,
                    limits=BASELINE_LIMITS)
                CourseDataGrant.objects.filter(pk=self.access.pk).update(active=True)
                self.requester.refresh_from_db()

    def test_two_postgres_approvers_mint_one_server_grant_and_record_the_loser(self):
        row = self.submit()
        other = CTFUser.objects.create_user(username='reveal-request-second-reviewer', role='teacher')
        CourseDataGrant.objects.create(actor=other, student=self.requester, course=self.course,
            granted_by=self.reviewer, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        barrier = Barrier(2)

        def approve(user):
            close_old_connections()
            try:
                context = ProtectionContext(schema_version=ProtectionContext.SCHEMA,
                    actor_ref='user/' + str(user.pk), role=Role.TEACHER,
                    authorization_ref='authorization/concurrent-' + uuid4().hex, scope_refs=('reveal-requests',),
                    environment=Environment.EVALUATION, domain='ctf', outlet=Outlet.API,
                    purpose=Purpose.INVESTIGATION, object_ref=row.request_ref, object_version='v1',
                    source_ref=None, source_version=None, source_hash=None, trace_id='trace/' + uuid4().hex)
                flow = self.components['reveal_requests']()
                barrier.wait(timeout=30)
                return flow.decide(row.request_ref, context, approved=True)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = [future.result(timeout=90) for future in
                       (workers.submit(approve, self.reviewer), workers.submit(approve, other))]
        success, = [result for result in results if isinstance(result, RevealRequestRecord)]
        denied, = [result for result in results if isinstance(result, ProtectionError)]
        self.assertIs(denied.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertNotEqual(success.subject_ref, success.decided_by)
        row.refresh_from_db()
        self.assertEqual(row.grant_document, success.grant.to_wire())
        self.assertEqual(row.decision_event_ref, success.decision_event_ref)
        events = self.events(row.request_ref, action='approve')
        self.assertEqual(len(events), 2)
        self.assertEqual({event.outcome for event in events}, {Outcome.SUCCEEDED, Outcome.DENIED})
        self.assertEqual(RevealRequest.objects.exclude(grant_id=None).count(), 1)

    def test_legal_application_and_approval_keep_existing_reviewer_and_owner_rules(self):
        CTFUser.objects.filter(pk=self.requester.pk).update(role='teacher')
        self.requester.refresh_from_db()
        task = LegalAnalysisTask.objects.create(created_by=self.requester, input_text=MARKER)
        report = LegalReport.objects.create(task=task, generated_by=self.admin, content=json.dumps({'evidence': MARKER}))
        for target, category, reference in ((task, RevealField.EVIDENCE, 'legal.legalanalysistask/input_text'),
                                             (report, RevealField.REPORT, 'legal.legalreport/content')):
            with self.subTest(reference=reference):
                row = self.submit(target=target, fields=[[category.value, reference]])
                self.approve(row)
                response = self.post(self.requester, request_ref=row.request_ref, action='read')
                self.assertEqual(response.status_code, 200)
                self.assertIn(reference, response.data['originals'])
                self.assertIn(MARKER, json.dumps(response.data['originals']))
        CTFUser.objects.filter(pk=self.requester.pk).update(role='student')
        self.requester.refresh_from_db()
        response = self.post(self.requester, data=self.body(task,
            fields=[[RevealField.EVIDENCE.value, 'legal.legalanalysistask/input_text']]))
        self.assertEqual(response.status_code, 403)

    def test_metadata_migration_roundtrip_preserves_only_synthetic_old_request_rows(self):
        before = [('security_policies', '0013_reveal_request')]
        after = [('security_policies', '0014_reveal_request_metadata')]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            old_model = executor.loader.project_state(before).apps.get_model('security_policies', 'RevealRequest')
            old = old_model.objects.create(requested_by_id=self.requester.pk, course_id=self.course.pk,
                object_ref=str(self.requester.security_uuid), object_version='v1',
                fields=[[RevealField.EMAIL.value, 'users.ctfuser/email']], purpose_ref='purpose/investigation',
                reason='合成已保护旧申请', requested_at=datetime.now(timezone.utc))
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            new_model = executor.loader.project_state(after).apps.get_model('security_policies', 'RevealRequest')
            evolved = new_model.objects.get(pk=old.pk)
            for name in ('request_ref', 'decided_by_ref', 'decided_at', 'decision_event_ref'):
                self.assertIsNone(getattr(evolved, name))
            self.assertEqual(evolved.reason, '合成已保护旧申请')
            evolved.request_ref = 'synthetic-migration-request'
            evolved.save(update_fields=['request_ref'])
            executor = MigrationExecutor(connection)
            executor.migrate(before)
            old_model = executor.loader.project_state(before).apps.get_model('security_policies', 'RevealRequest')
            self.assertEqual(old_model.objects.get(pk=old.pk).reason, '合成已保护旧申请')
        finally:
            MigrationExecutor(connection).migrate(after)
        with connection.cursor() as cursor:
            columns = {column.name for column in connection.introspection.get_table_description(
                cursor, RevealRequest._meta.db_table)}
        self.assertTrue({'request_ref', 'decided_by_ref', 'decided_at', 'decision_event_ref'} <= columns)

    def test_unique_bootstrap_binds_only_explicit_evaluation_capability_and_state(self):
        from challenges.views import proxy_challenge_view
        patches = (
            'rag_ingestion.registry.bind_ingestion', 'data_security.adapters.django.rag.bind_rag_protection',
            'data_security.adapters.django.private_files.bind_private_files',
            'data_security.adapters.django.recovery_ingress.bind_recovery_admission',
            'data_security.adapters.django.authentication.bind_bootstrap_teacher_inputs',
            'data_security.adapters.django.content.bind_content_protection',
            'data_security.adapters.django.logging.install_safe_logging', 'ai_providers.bind_manager',
            'audit.bridge.bind', 'export_risk.decisions.outbox.bind', 'ctfsafe.encryption.bind_field_crypto',
            'data_security.adapters.django.export_recovery.bind_export_recovery',
            'data_security.adapters.django.export_delivery.bind_export_delivery',
        )
        with ExitStack() as stack:
            for name in patches:
                stack.enter_context(patch(name))
            stack.enter_context(patch.object(APIView, 'authentication_classes', APIView.authentication_classes))
            stack.enter_context(patch.object(api_settings, 'DEFAULT_AUTHENTICATION_CLASSES',
                                             api_settings.DEFAULT_AUTHENTICATION_CLASSES))
            stack.enter_context(patch.object(proxy_challenge_view.cls, 'authentication_classes',
                                             proxy_challenge_view.cls.authentication_classes))
            stack.enter_context(override_settings(MIDDLEWARE=list(settings.MIDDLEWARE),
                REST_FRAMEWORK=dict(settings.REST_FRAMEWORK), DATA_SECURITY_FORMAL_MODE=False))
            stack.enter_context(patch.dict(bootstrap.os.environ, {'DATA_SECURITY_CONFIG': str(self.path)}))
            for options, enabled in ((None, False), ({'enabled': False}, False), ({'enabled': True}, True)):
                if options is None:
                    self.config.pop('reveal_requests', None)
                else:
                    self.config['reveal_requests'] = options
                self.path.write_text(json.dumps(self.config))
                components = bootstrap.assemble(config_path=self.path)
                self.assertEqual(components['reveal_requests'] is not None, enabled)
                with patch.object(bootstrap, 'assemble', return_value=components):
                    bootstrap.start_application()
                self.client.force_authenticate(user=self.admin)
                metadata = self.client.get('/api/data-security/policies/')
                self.assertEqual(metadata.status_code, 200)
                self.assertEqual(metadata.data['reveal_enabled'], enabled)
                self.assertEqual(metadata.data['reveal_state'], 'enabled-unverified' if enabled else 'disabled')
                self.client.force_authenticate(user=self.requester)
                response = self.client.get(BASE)
                self.assertEqual(response.status_code, 200 if enabled else 503)
            bootstrap.os.environ.pop('DATA_SECURITY_CONFIG')
            bootstrap.start_application()
            self.assertIsNone(reveal_api._binding)
        for options in ({'enabled': 1}, {'enabled': True, 'accepted': True}):
            with self.subTest(options=options), self.assertRaises(ContractViolation):
                self.config['reveal_requests'] = options
                self.path.write_text(json.dumps(self.config))
                bootstrap.assemble(config_path=self.path)
