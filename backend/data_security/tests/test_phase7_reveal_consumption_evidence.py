"""Exact consumption evidence on synthetic PG owners and the original reveal UoW."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.test import TransactionTestCase

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence import fields as field_module
from data_security.adapters.persistence.models import RevealRequest
from data_security.adapters.persistence.uow import DjangoUnitOfWork
from data_security.contracts import (
    BASELINE_LIMITS, BoundedPayload, Environment, EventKind, GrantState, MediaType, Outcome, Outlet,
    PayloadKind, PolicySnapshot, ProtectionContext, ProtectionError, Purpose, ReasonCode, RevealField,
    RevealRequestRecord, Role, SecurityEventV2, canonical_bytes, content_hash,
)
from data_security.tests.phase4_fixtures import field_configuration
from learning_paths.models import LearningPath
from users.models import CTFUser, CourseDataGrant


MARKER = 'consumption-proof@example.invalid'


class RevealConsumptionEvidenceTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
        self.path, self.config, _, binding = self.enterContext(field_configuration())
        policy_path = Path(self.config['policy_file'])
        policy = PolicySnapshot.from_json(policy_path.read_bytes())
        rules = policy.rules + tuple(replace(rule, role=role, purpose=Purpose.INVESTIGATION)
            for rule in policy.rules if rule.outlet is Outlet.API for role in (Role.STUDENT, Role.TEACHER))
        values = dict(policy.content(), version='phase7-consumption-synthetic.v1', rules=rules)
        digest = content_hash(values)
        policy = PolicySnapshot(**values, status=policy.status, content_hash=digest,
            approval=replace(policy.approval, approval_ref='approval/phase7-consumption-synthetic', content_hash=digest))
        policy_path.write_text(json.dumps(policy.to_wire()))
        self.config['policy_binding'] = replace(binding, protection_version=policy.version,
                                                protection_hash=digest).to_wire()
        checkpoints = self.path.parent / 'consumption-checkpoints'
        checkpoints.mkdir(mode=0o700)
        checkpoints.chmod(0o700)
        self.config['audit_chain'] = {
            'chain_version': 'ds.audit.v2', 'project_ref': 'phase7/consumption-synthetic',
            'object_uuid': '00000000-0000-4000-8000-000000000027', 'object_version': 'v1',
            'authorization_ref': 'authorization/phase7-consumption-synthetic', 'retained_keys': [],
            'checkpoint_root': str(checkpoints), 'checkpoint_ref': None,
        }
        self.config['reveal_requests'] = {'enabled': True}
        self.path.write_text(json.dumps(self.config))
        self.components = assemble(config_path=self.path)
        self.enterContext(patch.object(field_module, '_adapter', self.components['fields']))
        self.requester = CTFUser.objects.create_user(username='consumption-owner', email=MARKER, role='student')
        self.reviewer = CTFUser.objects.create_user(username='consumption-reviewer', role='teacher', is_staff=True)
        self.course = LearningPath.objects.create(title='合成消费课程', slug='consumption-synthetic',
                                                   description='隔离合成课程', difficulty='AP')
        CourseDataGrant.objects.create(actor=self.reviewer, student=self.requester, course=self.course,
            granted_by=self.reviewer, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    def context(self, actor):
        return ProtectionContext(schema_version=ProtectionContext.SCHEMA,
            actor_ref='user/' + str(actor.pk), role=Role(actor.role),
            authorization_ref='authorization/reveal-request-' + uuid4().hex,
            scope_refs=('users.ctfuser/email',), environment=Environment.EVALUATION, domain='ctf',
            outlet=Outlet.API, purpose=Purpose.INVESTIGATION, object_ref=str(self.requester.security_uuid),
            object_version='v' + str(self.requester.security_revision), source_ref=None,
            source_version=None, source_hash=None, trace_id='trace/' + uuid4().hex)

    def approved(self):
        context = self.context(self.requester)
        record = RevealRequestRecord(schema_version=RevealRequestRecord.SCHEMA,
            request_ref='request/' + uuid4().hex, subject_ref=context.actor_ref, course_id=self.course.pk,
            object_ref=context.object_ref, object_version=context.object_version,
            fields=((RevealField.EMAIL, 'users.ctfuser/email'),), purpose_ref='purpose/investigation',
            reason=BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.TEXT,
                media_type=MediaType.TEXT, text='核对合成资料 ' + MARKER, tree=None, binary=None, limits=BASELINE_LIMITS),
            requested_at=self.components['clock'](), state='pending', grant=None,
            decided_by=None, decided_at=None, decision_event_ref=None)
        factory = self.components['reveal_requests']
        pending = factory().request(record, context)
        self.assertIsInstance(pending, RevealRequestRecord)
        approved = factory().decide(pending.request_ref, self.context(self.reviewer), approved=True)
        self.assertIsInstance(approved, RevealRequestRecord)
        event = self.components['audit'].sink.read_authenticated(approved.decision_event_ref)
        self.assertIsInstance(event, SecurityEventV2)
        self.assertEqual(event.algorithm_versions, ('ds.reveal-request.v1', 'approve'))
        self.assertEqual(approved.grant.expires_at - approved.grant.issued_at, timedelta(seconds=900))
        return approved, factory()

    def successful_event(self, grant):
        row = SecurityAuditRecord.objects.get(event__kind='reveal', event__outcome='succeeded',
                                              event__correlation_ref=grant.grant_id)
        event = SecurityEventV2.from_wire(row.event)
        self.assertEqual(self.components['audit'].sink.read_authenticated(event.event_id), event)
        self.assertEqual(event.algorithm_versions, ('ds.reveal.v2',))
        self.assertNotIn(MARKER, json.dumps(event.to_wire()))
        return event

    def assert_rolled_back(self, approved, code):
        row = RevealRequest.objects.get(request_ref=approved.request_ref)
        self.assertEqual(row.state, 'approved')
        self.assertIsNone(row.consumed_at)
        self.assertEqual(row.grant_document, approved.grant.to_wire())
        events = SecurityAuditRecord.objects.filter(event__kind='reveal',
            event__correlation_ref=approved.grant.grant_id)
        self.assertFalse(events.filter(event__outcome='succeeded').exists())
        event = SecurityEventV2.from_wire(events.get().event)
        self.assertEqual(event.reason, code)
        self.assertEqual(event.algorithm_versions, ('ds.reveal.v1',))
        self.assertEqual(event.evidence_hashes, ())
        self.assertEqual(self.components['audit'].sink.read_authenticated(event.event_id), event)

    def test_request_read_binds_exact_consumption_separately_from_event_time(self):
        approved, flow = self.approved()
        started = datetime.now(timezone.utc)
        consumed_at, event_at = started + timedelta(microseconds=1), started + timedelta(microseconds=2)
        ticks = iter((started, event_at))
        flow.clock, flow.repository.clock = lambda: next(ticks), lambda: consumed_at
        result = flow.reveal_request(approved.request_ref, self.context(self.requester))
        self.assertIsInstance(result, BoundedPayload)
        self.assertEqual(result.tree.to_value(), {'users.ctfuser/email': MARKER})
        consumed, source = flow.repository._consumed, flow.repository._source
        self.assertEqual(consumed.state, GrantState.CONSUMED)
        self.assertEqual(consumed.consumed_at, consumed_at)
        row = RevealRequest.objects.get(request_ref=approved.request_ref)
        self.assertEqual(row.consumed_at, consumed_at)
        self.assertEqual(row.grant_document, approved.grant.to_wire())
        event = self.successful_event(approved.grant)
        self.assertEqual(event.occurred_at, event_at)
        self.assertNotEqual(event.occurred_at, row.consumed_at)
        self.assertEqual(event.evidence_hashes, (
            ('ciphertext', hashlib.sha256(canonical_bytes(source, include_payload=True)).hexdigest()),
            ('report', content_hash(consumed)),
        ))
        self.assertNotEqual(dict(event.evidence_hashes)['report'], content_hash(approved.grant))
        self.assertNotEqual(dict(event.evidence_hashes)['report'], content_hash(replace(consumed,
            consumed_at=consumed_at + timedelta(microseconds=1))))
        self.assertEqual(event.key_versions, tuple(dict.fromkeys(envelope.key.key_ref for _, envelope in source.fields)))

    def test_direct_read_has_v2_evidence_and_retry_keeps_the_original_consumption(self):
        approved, flow = self.approved()
        context = replace(self.context(self.requester), authorization_ref=approved.grant.authorization_ref)
        result = flow.reveal(approved.grant, context)
        self.assertIsInstance(result, BoundedPayload)
        self.assertEqual(result.tree.to_value(), {'users.ctfuser/email': MARKER})
        consumed = flow.repository._consumed
        event = self.successful_event(approved.grant)
        self.assertEqual(dict(event.evidence_hashes)['report'], content_hash(consumed))
        retry = self.components['reveal_requests']().reveal(approved.grant,
            replace(context, trace_id='trace/' + uuid4().hex))
        self.assertIsInstance(retry, ProtectionError)
        self.assertEqual(retry.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.successful_event(approved.grant), event)
        row = RevealRequest.objects.get(request_ref=approved.request_ref)
        self.assertEqual(row.consumed_at, consumed.consumed_at)
        self.assertEqual(row.grant_document, approved.grant.to_wire())

    def test_open_failure_rolls_back_consumption_without_a_v2_success(self):
        approved, flow = self.approved()
        observed = []

        def refuse_open(*args):
            observed.append(RevealRequest.objects.get(request_ref=approved.request_ref).state)
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.CIPHERTEXT_INVALID,
                                   retryable=False, trace_id='synthetic/consumption-open')

        with patch.object(flow.crypto, 'open', side_effect=refuse_open):
            result = flow.reveal_request(approved.request_ref, self.context(self.requester))
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(result.code, ReasonCode.CIPHERTEXT_INVALID)
        self.assertEqual(observed, ['consumed'])
        self.assert_rolled_back(approved, ReasonCode.CIPHERTEXT_INVALID)

    def test_unconfirmed_v2_receipt_rolls_back_real_success_and_consumption(self):
        approved, flow = self.approved()
        record = flow.audit.record
        attempted = []

        def unconfirmed(event, durability):
            receipt = record(event, durability)
            if event.kind is EventKind.REVEAL and event.outcome is Outcome.SUCCEEDED:
                self.assertEqual(event.algorithm_versions, ('ds.reveal.v2',))
                self.assertTrue(AuthenticatedAuditEntry.objects.filter(record__event_id=event.event_id).exists())
                self.assertEqual(RevealRequest.objects.get(request_ref=approved.request_ref).state, 'consumed')
                attempted.append(event.event_id)
                return replace(receipt, event_id='f' * 64)
            return receipt

        with patch.object(flow.audit, 'record', side_effect=unconfirmed):
            result = flow.reveal_request(approved.request_ref, self.context(self.requester))
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(len(attempted), 1)
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id=attempted[0]).exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.filter(record__event_id=attempted[0]).exists())
        self.assert_rolled_back(approved, ReasonCode.AUDIT_UNAVAILABLE)

    def test_precommit_failure_rolls_back_v2_fact_and_consumption(self):
        approved, flow = self.approved()
        attempted = []

        def refuse_commit(work):
            event = self.successful_event(approved.grant)
            attempted.append(event.event_id)
            self.assertEqual(RevealRequest.objects.get(request_ref=approved.request_ref).state, 'consumed')
            raise RuntimeError('synthetic precommit failure, not a PG COMMIT failure')

        with patch.object(DjangoUnitOfWork, 'commit', refuse_commit):
            result = flow.reveal_request(approved.request_ref, self.context(self.requester))
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(len(attempted), 1)
        self.assertFalse(SecurityAuditRecord.objects.filter(event_id=attempted[0]).exists())
        self.assertFalse(AuthenticatedAuditEntry.objects.filter(record__event_id=attempted[0]).exists())
        self.assert_rolled_back(approved, ReasonCode.AUTHORIZATION_DENIED)
