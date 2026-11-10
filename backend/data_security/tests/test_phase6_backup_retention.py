from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from data_security.application.backup_retention import BackupRetention
from data_security.contracts import (
    BASELINE_LIMITS, BackupRetentionRecord, ContractViolation, ProtectionContext, ProtectionError, ReasonCode,
)
from data_security.tests.fixtures import examples
from tools.data_security.dependencies import check_source


class BackupRetentionTests(unittest.TestCase):
    def setUp(self):
        self.template = examples()[BackupRetentionRecord]
        self.context = examples()[ProtectionContext]
        self.records, self.retired = [], []
        def retire(record, context):
            self.retired.append(record)
            return record.backup.object_ref
        self.port = SimpleNamespace(retention_inventory=lambda context, limits: tuple(self.records), retire=retire)
        self.owner = BackupRetention(backups=self.port, limits=BASELINE_LIMITS)

    def record(self, number, created_at, cadence):
        return replace(self.template, backup=replace(self.template.backup,
            object_ref='backup/' + format(number, '032x')), created_at=created_at, cadence=cadence)

    def test_seven_daily_and_four_weekly_are_independent_counts_not_age_windows(self):
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        self.records = [self.record(i, start + timedelta(days=i), 'daily') for i in range(9)]
        self.records += [self.record(20 + i, start + timedelta(weeks=i), 'weekly') for i in range(6)]
        expired = self.owner.preview(self.context)
        self.assertEqual(set(expired), {self.records[i] for i in (0, 1, 9, 10)})
        self.assertEqual(len(self.records) - len(expired), 11)
        self.assertFalse(self.retired)
        self.assertEqual(len(self.owner.apply(expired, self.context)), 4)
        self.assertEqual(tuple(self.retired), expired)

    def test_periods_use_utc_and_iso_week_year_with_one_latest_sample_per_slot(self):
        utc = timezone.utc
        self.records = [
            self.record(1, datetime(2021, 1, 3, 23, tzinfo=utc), 'weekly'),
            self.record(2, datetime(2021, 1, 4, 0, tzinfo=utc), 'weekly'),
            self.record(3, datetime(2021, 1, 4, 1, tzinfo=timezone(timedelta(hours=8))).astimezone(utc), 'weekly'),
            self.record(4, datetime(2021, 1, 4, 0, tzinfo=utc), 'daily'),
            self.record(5, datetime(2021, 1, 4, 1, tzinfo=utc), 'daily'),
        ]
        self.assertEqual(set(self.owner.preview(self.context)), {self.records[2], self.records[3]})

    def test_changed_inventory_or_wrong_approval_cannot_delete(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.records = [self.record(i, start + timedelta(days=i), 'daily') for i in range(8)]
        approved = self.owner.preview(self.context)
        self.records.append(self.record(9, start + timedelta(days=9), 'daily'))
        self.assertEqual(self.owner.apply(approved, self.context).code, ReasonCode.REPORT_MISMATCH)
        self.assertFalse(self.retired)

    def test_inventory_and_partial_retirement_errors_stop_the_batch(self):
        error = ProtectionError(schema_version=ProtectionError.SCHEMA,
            code=ReasonCode.DELIVERY_UNKNOWN, retryable=False, trace_id='backup/test')
        self.port.retention_inventory = lambda context, limits: error
        self.assertIs(self.owner.preview(self.context), error)
        self.assertIs(self.owner.apply((), self.context), error)
        self.assertFalse(self.retired)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.records = [self.record(i, start + timedelta(days=i), 'daily') for i in range(10)]
        self.port.retention_inventory = lambda context, limits: tuple(self.records)
        def fail(record, context):
            self.retired.append(record)
            return error
        self.port.retire = fail
        self.assertIs(self.owner.apply(self.owner.preview(self.context), self.context), error)
        self.assertEqual(len(self.retired), 1)

    def test_record_is_server_only_and_rejects_unsupported_cadence_or_naive_time(self):
        with self.assertRaises(ContractViolation):
            BackupRetentionRecord.from_wire(self.template.to_wire())
        for changes in ({'cadence': 'monthly'}, {'created_at': datetime(2026, 1, 1)},
                        {'files_size': -1}, {'backup': replace(self.template.backup, version='v1')}):
            with self.subTest(changes=tuple(changes)), self.assertRaises(ContractViolation):
                replace(self.template, **changes)

    def test_retention_policy_has_no_filesystem_database_or_adapter_dependencies(self):
        source = 'backend/data_security/application/backup_retention.py'
        self.assertFalse(check_source(source, 'from data_security.contracts import BackupRetentionRecord', phase=6))
        for target in ('os', 'pathlib', 'django.db', 'data_security.adapters.persistence.backup', 'subprocess'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))
