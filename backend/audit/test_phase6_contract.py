"""Shared AuditSink contract on real PostgreSQL and an owned checkpoint directory."""
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase

from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.tests.audit_contract import AuditSinkContract
from .models import AuditEvent, AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord


class PostgresAuditSinkContractTests(AuditSinkContract, TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        temporary = tempfile.TemporaryDirectory(prefix='audit-contract-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.root.chmod(0o700)
        clock = patch('django.utils.timezone.now', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        # DateTimeField captures its default callable when the model is imported.
        ledger_clock = patch.object(AuditLedgerEntry._meta.get_field('created_at'),
                                    'get_default', side_effect=lambda: self.now)
        ledger_clock.start()
        self.addCleanup(ledger_clock.stop)
        super().setUp()

    def make_sink(self, *, checkpoints=True, **changes):
        values = dict(clock=lambda: self.now, crypto=self.crypto, key=self.key, context=self.context,
                      checkpoint_root=self.root if checkpoints else None)
        values.update(changes)
        return DjangoAuditSink(**values)

    def resources(self):
        self.assertEqual(SecurityAuditRecord.objects.count(), AuditEvent.objects.count())
        return (SecurityAuditRecord.objects.count(), AuthenticatedAuditEntry.objects.count(),
                AuditLedgerEntry.objects.count(), len(list(self.root.iterdir())))

    def change_record(self, event_id, **changes):
        rows = SecurityAuditRecord.objects.filter(event_id=event_id)
        original = rows.values(*changes).get()
        rows.update(**changes)
        return original

    def change_entry(self, receipt, **changes):
        rows = AuthenticatedAuditEntry.objects.filter(pk=int(receipt.entry_ref.rsplit('/', 1)[1]))
        original = rows.values(*changes).get()
        rows.update(**changes)
        return original

    def remove_entry(self, receipt):
        AuthenticatedAuditEntry.objects.filter(pk=int(receipt.entry_ref.rsplit('/', 1)[1])).delete()

    def checkpoint_bytes(self, ref):
        return (self.root / (ref.removeprefix('audit/checkpoint/') + '.json')).read_bytes()

    def put_checkpoint(self, ref, encoded):
        path = self.root / (ref.removeprefix('audit/checkpoint/') + '.json')
        path.write_bytes(encoded)
        path.chmod(0o600)
