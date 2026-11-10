"""Pure reveal orchestration; memory permissions/receipts are not PostgreSQL proof."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import os
from unittest import TestCase
from unittest.mock import patch

from data_security.application.crypto_service import CryptoService
from data_security.contracts import (
    BASELINE_LIMITS, Approval, AuditReceipt, BoundedPayload, ContractViolation,
    Durability, EventKind, GrantState, MediaType, ObjectContext, Outcome, Outlet,
    PayloadKind, ProtectionContext, ProtectionError, Purpose, ReasonCode,
    RevealField, RevealGrant, RevealSource, Role, SecurityEventV2, canonical_bytes, content_hash,
)
from data_security.tests.fixtures import AT, dto, examples
from data_security.tests.phase2_fixtures import FakeKeys, MemoryPolicy, policy, text, tree


MARKER = 'reveal-private@example.invalid'


def grant(**changes):
    values = dict(schema_version=RevealGrant.SCHEMA, grant_id='reveal/fixture',
        subject_ref='actor/requester', object_ref=examples()[ObjectContext].object_uuid,
        object_version='v4', fields=((RevealField.CONVERSATION, 'synthetic.conversation/body'),
                                   (RevealField.CONVERSATION, 'synthetic.conversation/metadata')),
        purpose_ref='purpose/investigation', authorization_ref='authorization/reveal-fixture',
        issued_at=AT, expires_at=AT + timedelta(seconds=900))
    values.update(changes)
    approval = dto(Approval, approval_ref='approval/reveal-fixture', requested_by=values['subject_ref'],
        approved_by='actor/reviewer', approved_at=AT, content_hash=content_hash(values))
    return RevealGrant(**values, approval=approval, state=GrantState.ACTIVE,
                       consumed_at=None, revoked_at=None)


class MemoryGrants:
    def __init__(self, value, calls):
        self.value, self.calls = value, calls
        self.current_version = value.object_version
        self.allowed = {value.subject_ref, value.approval.approved_by}

    def consume(self, value, context, expected_version, at):
        self.calls.append('consume')
        if (value != self.value or value.state is not GrantState.ACTIVE or
                not {value.subject_ref, value.approval.approved_by} <= self.allowed or
                expected_version != self.current_version):
            return dto(ProtectionError, code=ReasonCode.AUTHORIZATION_DENIED,
                       retryable=False, trace_id='reveal/memory')
        if not value.issued_at <= at < value.expires_at:
            return dto(ProtectionError, code=ReasonCode.AUTHORIZATION_EXPIRED,
                       retryable=False, trace_id='reveal/memory')
        self.value = replace(value, state=GrantState.CONSUMED, consumed_at=at)
        return self.value


class MemorySources:
    def __init__(self, repository, value, calls):
        self.repository, self.value, self.calls = repository, value, calls

    def read(self, value, context):
        self.calls.append('source')
        if self.repository.value != value or value.state is not GrantState.CONSUMED:
            return dto(ProtectionError, code=ReasonCode.AUTHORIZATION_DENIED,
                       retryable=False, trace_id='reveal/source-memory')
        return self.value


class MemoryLedger:
    def __init__(self, calls):
        self.calls, self.events = calls, []
        self.mode = 'v2'

    def record(self, event, durability):
        self.calls.append(('audit', event.outcome))
        self.events.append(event)
        mode = self.mode if event.outcome is Outcome.SUCCEEDED else 'v2'
        if mode == 'raise':
            raise RuntimeError(MARKER)
        if mode == 'none':
            return None
        if mode == 'error':
            return dto(ProtectionError, code=ReasonCode.AUDIT_UNAVAILABLE,
                       retryable=False, trace_id='reveal/audit-memory')
        if mode == 'durable':
            return dto(AuditReceipt, event_id=event.event_id, durability=Durability.DURABLE,
                stored_at=AT, chain_version=None, entry_ref=None, sequence=None,
                entry_hash=None, checkpoint_ref=None)
        return dto(AuditReceipt, event_id='0' * 64 if mode == 'wrong-event' else event.event_id,
            durability=durability, stored_at=AT, chain_version='v1' if mode == 'v1' else 'ds.audit.v2',
            entry_ref='audit/memory', sequence=len(self.events), entry_hash=content_hash(event), checkpoint_ref=None)


class MemoryWork:
    def __init__(self, repository, audit, calls):
        self.repository, self.audit, self.calls = repository, audit, calls
        self.committed = False

    def __enter__(self):
        self.previous = self.repository.value
        self.audit_count = len(self.audit.events)
        self.calls.append('begin')
        return self

    def commit(self):
        self.calls.append('commit')
        self.committed = True

    def __exit__(self, exc_type, exc, traceback):
        if not self.committed or exc_type is not None:
            self.repository.value = self.previous
            del self.audit.events[self.audit_count:]
            self.calls.append('rollback')


class RevealFlowTests(TestCase):
    def setUp(self):
        from data_security.application.reveal import RevealFlow

        self.grant = grant()
        original = replace(examples()[ObjectContext], field_ref='synthetic.conversation/body',
                           object_version='v1', authorization_ref='authorization/phase4-storage')
        metadata = replace(original, field_ref='synthetic.conversation/metadata', object_version='v2')
        self.context = replace(examples()[ProtectionContext], actor_ref=self.grant.subject_ref,
            authorization_ref=self.grant.authorization_ref, object_ref=self.grant.object_ref,
            object_version=self.grant.object_version, scope_refs=tuple(ref for _, ref in self.grant.fields),
            domain=original.project_ref, environment=original.environment, outlet=Outlet.API,
            purpose=Purpose.INVESTIGATION, role=Role.ADMIN, trace_id='reveal/attempt')
        self.calls = []
        self.keys = FakeKeys()
        self.crypto = CryptoService(keys=self.keys, service_identity='reveal/synthetic-test',
            random_bytes=os.urandom, environment=self.context.environment, limits=BASELINE_LIMITS)
        self.payloads = (text('Original ' + MARKER), tree({'contact': MARKER, 'approved': True}))
        from data_security.tests.phase2_fixtures import reference_key
        fields = tuple((context, self.crypto.seal(payload, context, reference_key()))
                       for context, payload in zip((original, metadata), self.payloads))
        self.source = dto(RevealSource, object_ref=self.grant.object_ref,
                          object_version=self.grant.object_version, fields=fields)
        self.repository = MemoryGrants(self.grant, self.calls)
        self.sources = MemorySources(self.repository, self.source, self.calls)
        self.audit = MemoryLedger(self.calls)
        snapshot, self.binding = policy(self.context)
        self.policies = MemoryPolicy(snapshot)
        self.now = AT
        self.flow = RevealFlow(repository=self.repository, sources=self.sources, crypto=self.crypto,
            policies=self.policies, policy_binding=self.binding, audit=self.audit,
            uow_factory=lambda: MemoryWork(self.repository, self.audit, self.calls),
            clock=lambda: self.now, limits=BASELINE_LIMITS)

    def test_decrypts_only_after_consumption_then_v2_audit_before_commit(self):
        def open_original(envelope, context, key):
            self.assertIs(self.repository.value.state, GrantState.CONSUMED)
            self.calls.append('decrypt')
            return original_open(envelope, context, key)

        original_open = self.crypto.open
        with patch.object(self.crypto, 'open', side_effect=open_original) as opened:
            result = self.flow.reveal(self.grant, self.context)
        self.assertIs(type(result), BoundedPayload)
        self.assertEqual(result.tree.to_value(), dict(zip(self.context.scope_refs,
            (self.payloads[0].text, self.payloads[1].tree.to_value()))))
        self.assertEqual(self.calls, ['begin', 'consume', 'source', 'decrypt', 'decrypt',
                                    ('audit', Outcome.SUCCEEDED), 'commit'])
        self.assertEqual([call.args[1].object_version for call in opened.call_args_list], ['v1', 'v2'])
        self.assertTrue(all(call.args[1].authorization_ref == 'authorization/phase4-storage'
                            for call in opened.call_args_list))
        self.assertIs(self.repository.value.state, GrantState.CONSUMED)
        self.assertEqual(self.repository.value.consumed_at, AT)
        event = self.audit.events[0]
        self.assertIs(type(event), SecurityEventV2)
        self.assertIs(event.kind, EventKind.REVEAL)
        self.assertEqual(event.counts, (('records', 2),))
        self.assertEqual(event.algorithm_versions, ('ds.reveal.v2',))
        self.assertEqual(event.evidence_hashes, (
            ('ciphertext', hashlib.sha256(canonical_bytes(self.source, include_payload=True)).hexdigest()),
            ('report', content_hash(self.repository.value)),
        ))
        self.assertNotIn(MARKER, str(event.to_wire()))
        with self.assertRaises(ContractViolation) as error:
            result.to_wire()
        self.assertIs(error.exception.code, ReasonCode.SENSITIVE_SERIALIZATION_FORBIDDEN)

    def test_request_context_mismatches_stop_before_consuming_or_decrypting(self):
        cases = ({'actor_ref': 'actor/other'}, {'authorization_ref': 'authorization/other'},
            {'object_ref': 'object/other'}, {'object_version': 'v5'}, {'purpose': Purpose.TEACHING},
            {'outlet': Outlet.MODEL}, {'scope_refs': (self.context.scope_refs[0],)})
        with patch.object(self.crypto, 'open', wraps=self.crypto.open) as opened:
            for changes in cases:
                with self.subTest(changes=tuple(changes)):
                    result = self.flow.reveal(self.grant, replace(self.context, **changes))
                    self.assertIs(type(result), ProtectionError)
                    self.assertIs(result.code, ReasonCode.AUTHORIZATION_DENIED)
            opened.assert_not_called()
        self.assertNotIn('consume', self.calls)
        self.assertNotIn('source', self.calls)
        self.assertTrue(all(event.outcome is Outcome.DENIED for event in self.audit.events))

    def test_both_current_owner_permissions_are_required_not_an_admin_role(self):
        with patch.object(self.crypto, 'open', wraps=self.crypto.open) as opened:
            for removed in (self.grant.subject_ref, self.grant.approval.approved_by):
                self.repository.allowed = {'actor/requester', 'actor/reviewer'} - {removed}
                result = self.flow.reveal(self.grant, self.context)
                self.assertIs(result.code, ReasonCode.AUTHORIZATION_DENIED)
                self.assertIs(self.repository.value.state, GrantState.ACTIVE)
            opened.assert_not_called()
        self.assertNotIn('source', self.calls)
        self.assertNotIn('commit', self.calls)
        self.assertEqual(len(self.audit.events), 2)

    def test_expiry_revocation_version_change_and_replay_cannot_read_ciphertexts(self):
        revoked = replace(self.grant, state=GrantState.REVOKED, revoked_at=AT)
        consumed = replace(self.grant, state=GrantState.CONSUMED, consumed_at=AT)
        cases = ((self.grant, AT + timedelta(seconds=900), 'v4', ReasonCode.AUTHORIZATION_EXPIRED),
            (self.grant, AT - timedelta(seconds=1), 'v4', ReasonCode.AUTHORIZATION_EXPIRED),
            (revoked, AT, 'v4', ReasonCode.AUTHORIZATION_DENIED),
            (consumed, AT, 'v4', ReasonCode.AUTHORIZATION_DENIED),
            (self.grant, AT, 'v5', ReasonCode.AUTHORIZATION_DENIED))
        with patch.object(self.crypto, 'open', wraps=self.crypto.open) as opened:
            for value, at, version, code in cases:
                with self.subTest(state=value.state, at=at, version=version):
                    self.repository.value, self.now, self.repository.current_version = value, at, version
                    result = self.flow.reveal(value, self.context)
                    self.assertIs(result.code, code)
                    self.assertEqual(self.repository.value, value)
            opened.assert_not_called()
        self.assertNotIn('source', self.calls)
        self.assertNotIn('commit', self.calls)

    def test_consumption_acknowledgement_must_match_the_approved_grant(self):
        wrong = replace(grant(authorization_ref='authorization/other'),
                        state=GrantState.CONSUMED, consumed_at=AT)
        with patch.object(self.repository, 'consume', return_value=wrong), \
                patch.object(self.crypto, 'open', wraps=self.crypto.open) as opened:
            result = self.flow.reveal(self.grant, self.context)
            self.assertIs(result.code, ReasonCode.AUTHORIZATION_DENIED)
            opened.assert_not_called()
        self.assertNotIn('source', self.calls)
        self.assertNotIn('commit', self.calls)

    def test_wrong_source_scope_version_domain_or_environment_rolls_back(self):
        other_fields = tuple((replace(context, object_uuid='11111111-1111-4111-8111-111111111111'), envelope)
                             for context, envelope in self.source.fields)
        cases = (replace(self.source, object_ref='11111111-1111-4111-8111-111111111111', fields=other_fields),
            replace(self.source, object_version='v5'), replace(self.source, fields=self.source.fields[:1]),
            replace(self.source, fields=tuple(reversed(self.source.fields))),
            replace(self.source, fields=tuple((replace(context, project_ref='project/other'), envelope)
                                             for context, envelope in self.source.fields)),
            replace(self.source, fields=tuple((replace(context, environment=type(context.environment).EVALUATION), envelope)
                                             for context, envelope in self.source.fields)))
        with patch.object(self.crypto, 'open', wraps=self.crypto.open) as opened:
            for source in cases:
                with self.subTest(source=source.object_version):
                    self.sources.value = source
                    result = self.flow.reveal(self.grant, self.context)
                    self.assertIs(result.code, ReasonCode.AUTHORIZATION_DENIED)
                    self.assertIs(self.repository.value.state, GrantState.ACTIVE)
            opened.assert_not_called()
        self.assertNotIn('commit', self.calls)

    def test_bad_ciphertext_or_replaced_storage_aad_rolls_back_and_logs_no_plaintext(self):
        context, envelope = self.source.fields[0]
        corrupt = replace(envelope, ciphertext_and_tag=envelope.ciphertext_and_tag[:-1] +
                          bytes([envelope.ciphertext_and_tag[-1] ^ 1]))
        cases = (((context, corrupt), self.source.fields[1]),
            ((replace(context, object_version='v4'), envelope), self.source.fields[1]),
            ((context, replace(envelope, key=replace(envelope.key, key_ref='enc-data/v2', version='v2'))),
             self.source.fields[1]))
        for fields in cases:
            with self.subTest(version=fields[0][0].object_version):
                self.sources.value = replace(self.source, fields=fields)
                result = self.flow.reveal(self.grant, self.context)
                self.assertIs(result.code, ReasonCode.CIPHERTEXT_INVALID)
                self.assertIs(self.repository.value.state, GrantState.ACTIVE)
        self.assertNotIn('commit', self.calls)
        self.assertTrue(all(event.outcome is Outcome.FAILED for event in self.audit.events))
        self.assertNotIn(MARKER, str([event.to_wire() for event in self.audit.events]))

    def test_missing_weak_v1_or_wrong_event_receipts_cannot_release_plaintext(self):
        for mode in ('none', 'durable', 'v1', 'wrong-event', 'error', 'raise'):
            with self.subTest(mode=mode):
                self.audit.mode = mode
                result = self.flow.reveal(self.grant, self.context)
                self.assertIs(type(result), ProtectionError)
                self.assertIs(result.code, ReasonCode.AUDIT_UNAVAILABLE)
                self.assertIs(self.repository.value.state, GrantState.ACTIVE)
        self.assertNotIn('commit', self.calls)
        self.assertEqual(len(self.audit.events), 6)
        self.assertTrue(all(event.outcome is Outcome.FAILED for event in self.audit.events))
        self.assertNotIn(MARKER, str([event.to_wire() for event in self.audit.events]))

    def test_aggregate_limits_are_checked_before_audit_and_commit(self):
        self.flow.limits = replace(BASELINE_LIMITS, max_json_bytes=32)
        result = self.flow.reveal(self.grant, self.context)
        self.assertIs(result.code, ReasonCode.LIMIT_EXCEEDED)
        self.assertIs(self.repository.value.state, GrantState.ACTIVE)
        self.assertNotIn('commit', self.calls)
        self.assertEqual(len(self.audit.events), 1)
        self.assertIs(self.audit.events[0].outcome, Outcome.FAILED)

    def test_unapproved_policy_stops_before_consumption(self):
        failure = dto(ProtectionError, code=ReasonCode.POLICY_NOT_APPROVED,
                      retryable=False, trace_id='policy/memory')
        with patch.object(self.policies, 'snapshot', return_value=failure):
            result = self.flow.reveal(self.grant, self.context)
        self.assertIs(result.code, ReasonCode.POLICY_NOT_APPROVED)
        self.assertNotIn('consume', self.calls)
        self.assertNotIn('source', self.calls)
        self.assertNotIn('commit', self.calls)

    def test_unexpected_port_errors_return_a_fixed_error_without_the_exception_body(self):
        for target, method in ((self.repository, 'consume'), (self.sources, 'read'), (self.crypto, 'open')):
            with self.subTest(method=method), patch.object(target, method, side_effect=RuntimeError(MARKER)):
                result = self.flow.reveal(self.grant, self.context)
                self.assertIs(type(result), ProtectionError)
                self.assertFalse(result.retryable)
                self.assertIs(self.repository.value.state, GrantState.ACTIVE)
                self.assertNotIn(MARKER, str(result.to_wire()))
        self.assertNotIn('commit', self.calls)
        self.assertNotIn(MARKER, str([event.to_wire() for event in self.audit.events]))
