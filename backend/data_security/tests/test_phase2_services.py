from dataclasses import replace
from datetime import timedelta
import unittest

from data_security.contracts import *
from data_security.application.crypto_service import CryptoService
from data_security.application.protection import ProtectionService
from data_security.tests.phase2_fixtures import *


def crypto_service(keys=None, random_bytes=lambda n: bytes(range(n))):
    return CryptoService(keys=keys or FakeKeys(), service_identity='service/fixture', random_bytes=random_bytes,
                         environment=Environment.TEST, limits=BASELINE_LIMITS)


def protection_service(snapshot, audit=None, **kwargs):
    return ProtectionService(policies=MemoryPolicy(snapshot), audit=audit or MemoryAudit(), clock=lambda: AT,
        random_bytes=lambda n: bytes(n), environment=Environment.TEST, limits=BASELINE_LIMITS,
        field_ref='content/body', **kwargs)


class CryptoServiceTests(unittest.TestCase):
    def test_typed_roundtrip_empty_null_json_binary_and_determinism(self):
        service = crypto_service()
        obj, key = examples()[ObjectContext], reference_key()
        values = (text(''), text('🙂'), tree(None), tree(''), tree({'x': [None, '', 1, True]}),
            dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=MediaType.BINARY,
                binary=b'', text=None, tree=None, limits=BASELINE_LIMITS))
        envelopes = []
        for value in values:
            envelope = service.seal(value, obj, key)
            self.assertIsInstance(envelope, CipherEnvelope)
            self.assertEqual(service.open(envelope, obj, key), value)
            self.assertEqual(service.seal(value, obj, key), envelope)
            envelopes.append(envelope.ciphertext_and_tag)
        self.assertEqual(len(set(envelopes)), len(values))

    def test_keys_faults_wrong_use_bad_random_and_production_refused(self):
        obj, key = examples()[ObjectContext], reference_key()
        for error in (ReasonCode.KEY_UNAVAILABLE, ReasonCode.AUTHORIZATION_DENIED):
            service = crypto_service(FakeKeys(error))
            result = service.seal(text('data'), obj, key)
            self.assertIsInstance(result, ProtectionError)
            self.assertEqual(result.code, error)
        class Broken:
            def resolve(self, *args):
                raise RuntimeError(root_key().hex())
        self.assertIsInstance(crypto_service(Broken()).seal(text('data'), obj, key), ProtectionError)
        self.assertIsInstance(crypto_service(random_bytes=lambda n: b'').seal(text('data'), obj, key), ProtectionError)
        self.assertIsInstance(crypto_service().seal(text('data'), obj, reference_key(KeyPurpose.INDEX)), ProtectionError)
        self.assertIsInstance(crypto_service().seal(text('data'), replace(obj, environment=Environment.PRODUCTION), key), ProtectionError)
        with self.assertRaises(ContractViolation):
            CryptoService(keys=FakeKeys(), service_identity='service/test', random_bytes=lambda n: bytes(n),
                          environment=Environment.PRODUCTION, limits=BASELINE_LIMITS)

    def test_corruption_is_not_empty_or_original_data(self):
        obj, key = examples()[ObjectContext], reference_key()
        service = crypto_service()
        env = service.seal(text(''), obj, key)
        broken = replace(env, ciphertext_and_tag=bytes(len(env.ciphertext_and_tag)))
        self.assertIsInstance(service.open(broken, obj, key), ProtectionError)
        self.assertIsInstance(service.open('legacy plaintext', obj, key), ProtectionError)
        self.assertIsInstance(service.open(env, replace(obj, field_ref='other/field'), key), ProtectionError)

    def test_blind_index_is_stable_across_rows_not_fields_and_auth_is_separate(self):
        obj, service = examples()[ObjectContext], crypto_service()
        idx, mac = reference_key(KeyPurpose.INDEX), reference_key(KeyPurpose.AUDIT)
        result = service.blind_index(text('value'), obj, idx)
        self.assertIsInstance(result, bytes)
        self.assertEqual(result, service.blind_index(text('value'), replace(obj,
            object_uuid='00000000-0000-4000-8000-000000000002'), idx))
        self.assertNotEqual(result, service.blind_index(text('value'), replace(obj, field_ref='other/field'), idx))
        self.assertIsInstance(service.authenticate(b'metadata', obj, mac), bytes)
        self.assertIsInstance(service.authenticate(b'metadata', obj, idx), ProtectionError)
        self.assertEqual(len(service.keys.calls), 4)
        changed = replace(text('value'), limits=replace(BASELINE_LIMITS, max_actions=9999))
        self.assertEqual(result, service.blind_index(changed, obj, idx))


class ProtectionServiceTests(unittest.TestCase):
    def test_determinism_fixed_policy_clock_random_and_metadata_only_audit(self):
        snapshot, binding = policy()
        audit = MemoryAudit()
        service = protection_service(snapshot, audit)
        payload = text('contact a@example.invalid')
        first = service.protect(payload, context(), binding)
        self.assertIsInstance(first, ProtectedResult)
        self.assertEqual(first, service.protect(payload, context(), binding))
        self.assertEqual(first.payload.text, 'contact [REDACTED]')
        self.assertEqual(service.policies.calls, [binding] * 6)
        self.assertEqual(first.coverage.processed, 1)
        self.assertNotIn('example.invalid', canonical_bytes(audit.events[0]).decode('utf-8'))
        self.assertNotIn(payload.text, repr(first))

    def test_audit_rejection_and_exception_never_return_payload(self):
        snapshot, binding = policy()
        payload = text('a@example.invalid')
        class ThrowingAudit:
            def record(self, *args):
                raise RuntimeError(root_key().hex())
        for audit in (MemoryAudit(reject=True), ThrowingAudit()):
            service = protection_service(snapshot, audit)
            result = service.protect(payload, context(), binding)
            self.assertIsInstance(result, ProtectionError)
            self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
            self.assertNotIn('example.invalid', canonical_bytes(result).decode('utf-8'))
            self.assertNotIn(root_key().hex(), canonical_bytes(result).decode('utf-8'))

    def test_wrong_receipt_policy_expiry_and_no_default_fallback(self):
        snapshot, binding = policy()
        class WrongAudit(MemoryAudit):
            def record(self, event, durability):
                return replace(super().record(event, durability), event_id='event/wrong')
        service = protection_service(snapshot, WrongAudit())
        self.assertIsInstance(service.protect(text(''), context(), binding), ProtectionError)
        audit = MemoryAudit()
        service = protection_service(snapshot, audit)
        self.assertIsInstance(service.protect(text('a@example.invalid'), context(), replace(binding, protection_hash=HASH)), ProtectionError)
        self.assertFalse(audit.events)
        service.clock = lambda: snapshot.expires_at
        self.assertIsInstance(service.protect(text('a@example.invalid'), context(), binding), ProtectionError)
        class WrongPolicy:
            def snapshot(self, binding):
                raise RuntimeError('fixture fault')
        service.policies = WrongPolicy()
        self.assertIsInstance(service.protect(text('safe'), context(), binding), ProtectionError)
        self.assertFalse(audit.events)

    def test_key_port_errors_prevent_audit_and_cleartext_fallback(self):
        spec = algorithm(Algorithm.PSEUDONYM, key_ref='mask-pseudonym/v1', pseudonym_bits=128)
        snapshot, binding = policy(specs={Category.EMAIL: spec})
        audit = MemoryAudit()
        for keys in (FakeKeys(ReasonCode.KEY_UNAVAILABLE), FakeKeys()):
            service = protection_service(snapshot, audit, keys=keys,
                key_references=(reference_key(KeyPurpose.PSEUDONYM),))
            result = service.protect(text('a@example.invalid'), context(), binding)
            if keys.error:
                self.assertIsInstance(result, ProtectionError)
                self.assertFalse(audit.events)
            else:
                self.assertIsInstance(result, ProtectedResult)
                self.assertEqual(len(result.payload.text), 22)
        service = protection_service(snapshot, keys=FakeKeys())
        self.assertIsInstance(service.protect(text('a@example.invalid'), context(), binding), ProtectionError)

    def test_production_context_and_constructor_refuse_test_ports(self):
        snapshot, binding = policy()
        service = protection_service(snapshot)
        self.assertIsInstance(service.protect(text('safe'), replace(context(), environment=Environment.PRODUCTION), binding), ProtectionError)
        self.assertIsInstance(service.protect(text('safe'), None, binding), ProtectionError)
        with self.assertRaises(ContractViolation):
            ProtectionService(policies=MemoryPolicy(snapshot), audit=MemoryAudit(), clock=lambda: AT,
                random_bytes=lambda n: bytes(n), environment=Environment.PRODUCTION, limits=BASELINE_LIMITS, field_ref='content/body')

    def test_json_coverage_and_post_protection_truncation(self):
        snapshot, binding = policy()
        service = protection_service(snapshot, truncate=algorithm(Algorithm.TRUNCATE, max_length=8))
        result = service.protect(tree({'x': 'a@example.invalid', 'y': [None, 1, True]}), context(), binding)
        self.assertIsInstance(result, ProtectedResult)
        self.assertEqual(result.coverage.processed, 4)
        self.assertEqual(result.payload.tree.to_value()['x'], '[REDACTE')
        empty = service.protect(tree({}), context(), binding)
        self.assertIsNone(empty.coverage.ratio)

    def test_exact_binding_revocation_and_exception_expiry_before_return(self):
        snapshot, binding = policy()
        service = protection_service(snapshot)
        class RevokingPolicy(MemoryPolicy):
            def snapshot(self, requested):
                if self.calls:
                    return replace(self.value, status=PolicyStatus.RETIRED)
                return super().snapshot(requested)
        service.policies = RevokingPolicy(snapshot)
        self.assertIsInstance(service.protect(text('a@example.invalid'), context(), binding), ProtectionError)
        service = protection_service(snapshot)
        class RevokingAudit(MemoryAudit):
            def record(self, event, durability):
                service.policies.value = replace(snapshot, status=PolicyStatus.RETIRED)
                return super().record(event, durability)
        service.audit = RevokingAudit()
        self.assertIsInstance(service.protect(text('a@example.invalid'), context(), binding), ProtectionError)
        ctx = replace(context(), purpose=Purpose.TEACHING, source_ref='fixture/published',
                      source_version='v1', source_hash=HASH, scope_refs=('content/endpoint',))
        exception = examples()[TeachingException]
        values = exception.content()
        values['expires_at'] = AT + timedelta(seconds=1)
        exception = TeachingException(**values, approval=approval(content_hash(values)))
        snapshot, binding = policy(ctx, exceptions=(exception,))
        service = protection_service(snapshot)
        service.field_ref = 'content/endpoint'
        times = iter((AT, AT + timedelta(seconds=2)))
        service.clock = lambda: next(times)
        result = service.protect(text('198.51.100.7'), ctx, binding)
        self.assertIsInstance(result, ProtectionError)
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_EXPIRED)

    def test_unverified_memory_audit_never_returns_authenticated_events(self):
        event = examples()[SecurityEvent]
        for sink in (MemoryAudit(), MemoryAudit(reject=True)):
            sink.append(event, Durability.DURABLE)
            for event_id in (event.event_id, 'event/missing'):
                result = sink.read_authenticated(event_id)
                self.assertIsInstance(result, ProtectionError)
                self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
            self.assertEqual(sink.events, [event])

    def test_memory_repository_and_refusing_sink_same_port_semantics(self):
        snapshot, binding = policy()
        repo = MemoryPolicy(snapshot)
        self.assertEqual(repo.read(binding), repo.snapshot(binding))
        self.assertIsInstance(repo.put(snapshot, 'wrong'), ProtectionError)
        self.assertTrue(repo.put(snapshot, snapshot.version))
        sink = MemoryAudit(reject=True)
        event = examples()[SecurityEvent]
        self.assertEqual(sink.append(event, Durability.DURABLE), sink.record(event, Durability.DURABLE))
        self.assertIsInstance(repo.approve(snapshot, snapshot.approval, context()), ProtectionError)
        self.assertIsInstance(repo.retire(binding, context()), ProtectionError)
        for port in (MemoryAudit(), sink):
            self.assertIsInstance(port.verify('chain/fixture'), ProtectionError)
            self.assertIsInstance(port.checkpoint('chain/fixture'), ProtectionError)
            self.assertIsInstance(port.record(event, Durability.LEDGER_CONFIRMED), ProtectionError)
        for interface, instance in ((PolicyRepository, repo), (PolicyCatalogPort, repo),
                                    (AuditSink, sink), (AuditPort, sink), (KeyResolverPort, FakeKeys())):
            for name, member in vars(interface).items():
                if not name.startswith('_') and callable(member):
                    self.assertTrue(callable(getattr(instance, name, None)))
