"""Recovery wire, HMAC and checkpoint coverage on the existing authenticated chain."""
from dataclasses import replace

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.contracts import Durability, KeyPurpose, QuotaRecoveryEvent, ReasonCode, SecurityEventV2, content_hash
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import reference_key
from resources.test_phase6_private_store import PrivateStoreFixture


class RecoveryAuditPostgresTests(PrivateStoreFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql')
        self.root.chmod(0o700)
        self.sink = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
                                    context=self.context, checkpoint_root=self.root)
        self.event = examples()[QuotaRecoveryEvent]
        self.receipt = self.sink.append(self.event, Durability.LEDGER_CONFIRMED)
        self.assertEqual(self.sink.verify('ds.audit.v2'), self.receipt)

    def test_malformed_persisted_event_shapes_return_typed_failure(self):
        for value in ([], 'invalid', 42, {}, {'schema_version': 'unknown/event'}):
            with self.subTest(value=value):
                SecurityAuditRecord.objects.update(event=value)
                self.denied(self.sink.verify('ds.audit.v2'), ReasonCode.AUDIT_UNAVAILABLE)
                self.denied(self.sink.checkpoint('ds.audit.v2'), ReasonCode.AUDIT_UNAVAILABLE)
                self.denied(self.sink.append(replace(self.event, event_id='after/corruption'),
                    Durability.LEDGER_CONFIRMED), ReasonCode.AUDIT_UNAVAILABLE)
                self.assertEqual(SecurityAuditRecord.objects.count(), 1)
                self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_recomputed_unkeyed_hashes_cannot_forge_recovery_operator(self):
        entry = AuthenticatedAuditEntry.objects.select_related('record').get()
        forged = replace(self.event, actor_ref='actor/forged', authorization_ref='grant/forged')
        entry.record.event = forged.to_wire()
        entry.record.save(update_fields=['event'])
        entry.event_hash = content_hash(forged)
        entry.current_hash = content_hash({'content': self.sink._entry_content(entry),
                                            'authentication': bytes(entry.authentication)})
        entry.save(update_fields=['event_hash', 'current_hash'])
        self.denied(self.sink.verify('ds.audit.v2'), ReasonCode.AUDIT_UNAVAILABLE)

    def test_checkpoint_authenticates_recovery_prefix_and_later_observations(self):
        anchored = self.sink.checkpoint('ds.audit.v2')
        verifier = DjangoAuditSink(clock=timezone.now, crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
            context=self.context, checkpoint_root=self.root, checkpoint_ref=anchored.checkpoint_ref)
        self.assertEqual(verifier.verify('ds.audit.v2'), anchored)
        ordinary = self.sink.append(replace(examples()[SecurityEventV2], event_id='ordinary/v2'),
                                    Durability.LEDGER_CONFIRMED)
        self.assertEqual(ordinary.sequence, 2)
        self.assertEqual(verifier.verify('ds.audit.v2'), replace(ordinary, checkpoint_ref=anchored.checkpoint_ref))
        second = self.sink.append(replace(self.event, event_id='second/recovery', occurred_at=timezone.now()),
                                  Durability.LEDGER_CONFIRMED)
        self.assertEqual(verifier.verify('ds.audit.v2'), replace(second, checkpoint_ref=anchored.checkpoint_ref))
