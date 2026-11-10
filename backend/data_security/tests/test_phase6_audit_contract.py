"""Stateful in-memory AuditSink exercising the shared port contract."""
from unittest import TestCase

from data_security.tests.audit_contract import AuditSinkContract
from data_security.tests.audit_memory import MemoryAuditSink


class MemoryAuditSinkContractTests(AuditSinkContract, TestCase):
    def setUp(self):
        self.records, self.entries, self.legacy, self.points = {}, [], [], {}
        super().setUp()

    def make_sink(self, *, checkpoints=True, **changes):
        values = dict(clock=lambda: self.now, crypto=self.crypto, key=self.key, context=self.context)
        values.update(changes)
        return MemoryAuditSink(records=self.records, entries=self.entries, legacy=self.legacy,
                               checkpoints=self.points if checkpoints else None, **values)

    def resources(self):
        return len(self.records), len(self.entries), len(self.legacy), len(self.points)

    def change_record(self, event_id, **changes):
        row = self.records[event_id]
        original = {key: row[key] for key in changes}
        row.update(changes)
        return original

    def change_entry(self, receipt, **changes):
        entry = next(e for e in self.entries if e['ref'] == receipt.entry_ref)
        original = {key: entry[key] for key in changes}
        entry.update(changes)
        return original

    def remove_entry(self, receipt):
        self.entries.remove(next(e for e in self.entries if e['ref'] == receipt.entry_ref))

    def checkpoint_bytes(self, ref):
        return self.points[ref]

    def put_checkpoint(self, ref, encoded):
        self.points[ref] = encoded
