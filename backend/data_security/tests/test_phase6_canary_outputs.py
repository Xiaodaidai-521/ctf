"""Final log/table output hooks, with explicit synthetic check authorities."""
import io
import logging
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock, patch

from data_security.adapters.django.logging import SafeLogFormatter, install_safe_logging
from data_security.adapters.tabular.codec import TableCodec
from data_security.application.canary import CanaryTools
from data_security.application.table_reports import ReportCandidate
from data_security.contracts import (BASELINE_LIMITS, BoundedPayload, ContractViolation, Outlet,
    ProtectionError, Purpose, ReasonCode, TableSnapshot)
from data_security.tests import test_phase6_table_reports as tables
from data_security.tests.test_phase3_audit_gateway import UnsafeRendering
from data_security.tests.test_phase5_codec import rewrite
from data_security.tests.test_phase6_canary import CanaryToolFixture


class CanaryLogTests(CanaryToolFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.context = replace(self.context, outlet=Outlet.LOG)
        self.checker = Mock(wraps=self.service)
        self.output = io.StringIO()
        self.handler = logging.StreamHandler(self.output)
        self.handler.setFormatter(SafeLogFormatter('%(message)s', canary=self.checker,
            canary_context=self.context, limits=BASELINE_LIMITS))

    def test_discarded_message_exception_and_extra_are_not_scanned_or_rendered(self):
        values = self.service.catalog[self.seed.seed_id][1].tree.to_value()['values']
        record = logging.LogRecord('test', logging.ERROR, '', 0, UnsafeRendering(),
            (UnsafeRendering(),), (RuntimeError, RuntimeError(' '.join(values.values())), None))
        record.exc_text = ' '.join(values.values())
        record.extra = UnsafeRendering()
        self.handler.handle(record)
        self.assertEqual(self.output.getvalue(), 'LOG_EXCEPTION_OMITTED\n')
        checked = self.checker.check.call_args.kwargs
        self.assertEqual(checked['payload'].text + '\n', self.output.getvalue())
        self.assertEqual(checked['context'], self.context)
        self.assertEqual(self.events, [])

    def test_fault_in_final_format_alerts_before_stream_write(self):
        values = self.service.catalog[self.seed.seed_id][1].tree.to_value()['values']
        with patch.object(logging.Formatter, 'format', return_value=' '.join(values.values())):
            self.handler.handle(logging.LogRecord('test', logging.INFO, '', 0, 'safe', (), None))
        self.assertEqual(self.output.getvalue(), 'LOG_CANARY_BLOCKED\n')
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0].counts, (('hit', 3),))
        self.assertIn('outlet/log', self.events[0].algorithm_versions)

    def test_check_errors_and_limits_emit_fixed_failure_without_recursive_logging(self):
        formatter = self.handler.formatter
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                  retryable=False, trace_id='synthetic/check')
        with patch.object(logging.Logger, '_log') as recursive, patch.object(self.handler, 'handleError') as error:
            for value in (failure, None, RuntimeError('synthetic failure')):
                formatter.canary = Mock()
                if isinstance(value, Exception):
                    formatter.canary.check.side_effect = value
                else:
                    formatter.canary.check.return_value = value
                self.handler.handle(logging.LogRecord('test', 20, '', 0, 'safe', (), None))
            formatter.canary = self.checker
            formatter.limits = replace(BASELINE_LIMITS, max_bytes=1)
            self.handler.handle(logging.LogRecord('test', 20, '', 0, 'safe', (), None))
            recursive.assert_not_called()
            error.assert_not_called()
        self.assertEqual(self.output.getvalue(), 'LOG_CANARY_CHECK_FAILED\n' * 4)
        self.checker.check.assert_not_called()

    def test_install_applies_to_child_output_handlers_and_requires_log_authority(self):
        parent = logging.getLogger('phase6-canary-log')
        child = parent.getChild('sdk')
        with patch.object(logging.getLogger(), 'handlers', []), \
                patch.object(logging.Logger.manager, 'loggerDict', {'parent': parent}), \
                patch.object(parent, 'handlers', [self.handler]), patch.object(parent, 'propagate', False), \
                patch.object(parent, 'level', logging.INFO), patch.object(child, 'level', logging.INFO):
            install_safe_logging(canary=self.checker, canary_context=self.context, limits=BASELINE_LIMITS)
            child.info('discarded')
        self.assertEqual(self.output.getvalue(), 'INFO LOG_MESSAGE_OMITTED\n')
        self.assertEqual(self.checker.check.call_count, 1)
        with self.assertRaises(ContractViolation):
            SafeLogFormatter(canary=self.service, canary_context=replace(self.context, outlet=Outlet.MODEL),
                             limits=BASELINE_LIMITS)


class CanaryTableTests(CanaryToolFixture, TestCase):
    load = tables.TableReportTests.load

    def setUp(self):
        super().setUp()
        self.check_context_template = self.context
        tables.TableReportTests.setUp(self)
        self.configure()

    def configure(self):
        self.seed = replace(self.seed, domain=self.execution.domain_ref)
        self.service = CanaryTools(**dict(self.options, seeds=(self.seed,), domain=self.seed.domain,
                                         policy_binding=self.plan.policy_binding))
        self.checker = Mock(wraps=self.service)
        self.executor.canary = self.checker
        self.check_context = replace(self.check_context_template, outlet=Outlet.EXPORT, purpose=Purpose.DELIVERY,
            actor_ref=self.execution.subject_ref, authorization_ref=self.execution.authorization_id,
            domain=self.execution.domain_ref, object_ref=self.context.object_uuid,
            object_version=self.context.object_version, trace_id=self.execution.execution_id)
        self.values = self.service.catalog[self.seed.seed_id][1].tree.to_value()['values']

    def prepare(self):
        return self.executor.prepare(self.payload, self.plan, self.execution, self.context,
                                     canary_context=self.check_context)

    def test_actual_csv_and_xlsx_output_and_retained_titles_have_clean_checks(self):
        for kind, fmt in (('mainline', 'csv'), ('legacy', 'csv'), ('legacy', 'xlsx')):
            self.load(kind, fmt)
            self.configure()
            result = self.prepare()
            self.assertIsInstance(result, ReportCandidate)
            calls = self.checker.check.call_args_list
            self.assertEqual(len(calls), 2)
            delivered, metadata = (call.kwargs['payload'] for call in calls)
            self.assertIs(type(delivered), TableSnapshot)
            self.assertIs(type(metadata), BoundedPayload)
            self.assertEqual(delivered.input_hash, result.report.output_hash)
            self.assertEqual(metadata.tree.to_value(), [] if fmt == 'csv' else ['Archive', '明细'])
            self.assertTrue(all(c.kwargs['context'] == self.check_context for c in calls))
        self.assertEqual(self.events, [])

    def test_literal_in_serialized_cell_alerts_before_encryption_or_storage(self):
        real = TableCodec.serialize
        def inject(codec, snapshot, limits):
            output = real(codec, snapshot, limits)
            changed = output.binary.replace(b'[EMAIL]', ' '.join(self.values.values()).encode(), 1)
            self.assertNotEqual(changed, output.binary)
            return replace(output, binary=changed)
        with patch.object(TableCodec, 'serialize', inject), patch.object(self.crypto, 'seal') as seal:
            result = self.prepare()
            self.assertEqual(result.code, ReasonCode.SCOPE_INCOMPLETE)
            seal.assert_not_called()
        self.assertEqual(self.store.calls, [])
        self.assertEqual(self.events[0].counts, (('hit', 3),))
        self.assertEqual(self.events[0].correlation_ref, self.execution.execution_id)
        self.assertIn('outlet/export', self.events[0].algorithm_versions)

    def test_literal_in_actual_xlsx_title_alerts_even_with_clean_cells(self):
        self.load('legacy', 'xlsx')
        self.configure()
        real = TableCodec.serialize
        def inject(codec, snapshot, limits):
            output = real(codec, snapshot, limits)
            changed = rewrite(output.binary, 'xl/workbook.xml',
                lambda value: value.replace('明细'.encode(), self.values['ip_address'].encode()))
            self.assertNotEqual(changed, output.binary)
            return replace(output, binary=changed)
        with patch.object(TableCodec, 'serialize', inject):
            result = self.prepare()
        self.assertEqual(result.code, ReasonCode.SCOPE_INCOMPLETE)
        self.assertEqual(self.checker.check.call_count, 2)
        self.assertEqual(self.events[0].counts, (('hit', 1),))
        self.assertEqual(self.store.calls, [])

    def test_missing_or_mismatched_check_authority_is_not_minted_from_object_context(self):
        for context in (None, True, replace(self.check_context, actor_ref='another/actor'),
                        replace(self.check_context, authorization_ref='another/grant'),
                        replace(self.check_context, object_version='another/version'),
                        replace(self.check_context, trace_id='another/execution'),
                        replace(self.check_context, outlet=Outlet.LOG)):
            result = self.executor.prepare(self.payload, self.plan, self.execution, self.context,
                                           canary_context=context)
            self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        self.checker.check.assert_not_called()
        self.assertEqual(self.store.calls, [])

    def test_check_failure_is_not_a_ready_candidate(self):
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                                  retryable=False, trace_id='synthetic/check')
        self.executor.canary = Mock()
        for value in (failure, None, False):
            self.executor.canary.check.return_value = value
            result = self.prepare()
            self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(self.store.calls, [])
