"""Retained server intent for reference-only recovery; never proof of zero effects."""
from dataclasses import replace
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase

from data_security.adapters.persistence.models import ExportReport
from data_security.adapters.persistence.report_records import DjangoReportRepository
from data_security.contracts import Environment, ExecutionBinding, ProtectionError, ReasonCode
from .test_phase6_report_records import ReportRecordFixture


class ExportBindingTests(ReportRecordFixture, TestCase):
    def test_begin_retains_complete_binding_before_any_report_or_delivery(self):
        record = self.record
        self.assertIs(self.repository.begin(record.plan, record.binding, record.context), True)
        row = ExportReport.objects.get()
        self.assertIsNone(row.document)
        self.assertIsNone(row.private_object_id)
        self.assertIsNone(row.delivery_receipt)
        self.assertEqual(row.binding_document, record.binding.to_wire())
        rebuilt = DjangoReportRepository(environment=Environment.TEST)
        self.assertEqual(rebuilt.load_binding(record.binding.execution_id), record.binding)
        self.assertEqual(ExportReport.objects.count(), 1)
        self.assertEqual(self.repository.put(record), record)
        self.assertEqual(rebuilt.load_binding(record.binding.execution_id), record.binding)

    def test_put_and_legacy_prepared_record_resolve_same_binding_without_rewriting(self):
        self.assertEqual(self.repository.put(self.record), self.record)
        before = ExportReport.objects.values().get()
        self.assertEqual(self.repository.load_binding(self.record.binding.execution_id), self.record.binding)
        self.assertEqual(ExportReport.objects.values().get(), before)
        ExportReport.objects.update(binding_document=None)
        before = ExportReport.objects.values().get()
        self.assertEqual(self.repository.load_binding(self.record.binding.execution_id), self.record.binding)
        self.assertEqual(ExportReport.objects.values().get(), before)

    def test_missing_intent_and_legacy_preparing_row_remain_unknown(self):
        binding = self.record.binding
        self.denied(self.repository.load_binding(binding.execution_id), ReasonCode.DELIVERY_UNKNOWN)
        self.repository.begin(self.record.plan, binding, self.record.context)
        ExportReport.objects.update(binding_document=None)
        self.denied(self.repository.load_binding(binding.execution_id), ReasonCode.DELIVERY_UNKNOWN)
        self.assertEqual(ExportReport.objects.get().state, 'preparing')
        self.assertIsNone(ExportReport.objects.get().delivery_receipt)

    def test_every_bound_identity_and_hash_is_checked_without_repair(self):
        binding = self.record.binding
        self.repository.begin(self.record.plan, binding, self.record.context)
        for changes in ({'quantity': binding.quantity + 1}, {'subject_ref': 'user/other'},
                        {'execution_id': 'execution/other'}, {'idempotency_key': 'key/other'},
                        {'authorization_id': 'authorization/other'}, {'request_id': 'request/other'}):
            document = replace(binding, **changes).to_wire()
            ExportReport.objects.update(binding_document=document)
            with self.subTest(field=next(iter(changes))):
                self.denied(self.repository.load_binding(binding.execution_id), ReasonCode.REPORT_MISMATCH)
                self.assertEqual(ExportReport.objects.get().binding_document, document)
        ExportReport.objects.update(binding_document=binding.to_wire(), binding_hash='0' * 64)
        self.denied(self.repository.load_binding(binding.execution_id), ReasonCode.REPORT_MISMATCH)

    def test_expired_binding_can_be_resolved_but_other_environment_cannot(self):
        # Recovery needs the original intent, not an unexpired delivery grant.
        self.repository.begin(self.record.plan, self.record.binding, self.record.context)
        self.assertEqual(self.repository.load_binding(self.record.binding.execution_id), self.record.binding)
        other = DjangoReportRepository(environment=Environment.EVALUATION)
        self.denied(other.load_binding(self.record.binding.execution_id), ReasonCode.SOURCE_NOT_APPROVED)

    def test_malformed_retained_binding_is_not_a_client_decode_bypass(self):
        binding = self.record.binding
        self.repository.begin(self.record.plan, binding, self.record.context)
        for document in ([], True, 'binding', {}, dict(binding.to_wire(), delivered_records=0)):
            ExportReport.objects.update(binding_document=document)
            with self.subTest(document_type=type(document).__name__):
                result = self.repository.load_binding(binding.execution_id)
                self.assertIs(type(result), ProtectionError)
                self.assertIsNot(type(result), ExecutionBinding)
                self.assertEqual(ExportReport.objects.get().binding_document, document)
        ExportReport.objects.update(binding_document=None, document=[])
        self.denied(self.repository.load_binding(binding.execution_id), ReasonCode.REPORT_MISMATCH)

    def test_database_failure_remains_unknown_without_creating_an_intent(self):
        with patch.object(ExportReport.objects, 'filter', side_effect=DatabaseError('synthetic failure')):
            self.denied(self.repository.load_binding(self.record.binding.execution_id), ReasonCode.DELIVERY_UNKNOWN)
        self.assertFalse(ExportReport.objects.exists())
