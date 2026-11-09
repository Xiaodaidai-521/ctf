"""Offline, synthetic-only audit entry and logging boundary tests."""
from dataclasses import replace
from datetime import timedelta
import io
import json
import logging
import unittest
from unittest.mock import Mock, patch

from audit import bridge
from data_security.application.audit_gateway import AuditGateway
from data_security.application.crypto_service import CryptoService
from data_security.adapters.django.logging import SafeLogFilter, SafeLogFormatter
from data_security.contracts import (AuditReceipt, BASELINE_LIMITS, ContractViolation, Durability,
    Environment, EventKind, KeyPurpose, ObjectContext, ProtectionError, ReasonCode, SecurityEvent)
from data_security.tests.fixtures import AT, HASH, dto, examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key


class AuditGatewayTests(unittest.TestCase):
    def setUp(self):
        self.event = examples()[SecurityEvent]
        self.receipt = examples()[AuditReceipt]
        self.sink = Mock()
        self.gateway = AuditGateway(sink=self.sink)

    def test_durable_has_no_ledger_claim(self):
        self.sink.append.return_value = self.receipt
        self.assertIs(self.gateway.record(self.event, Durability.DURABLE), self.receipt)
        self.sink.append.assert_called_once_with(self.event, Durability.DURABLE)
        self.assertIsNone(self.receipt.entry_hash)

    def test_confirmed_is_not_downgraded(self):
        confirmed = dto(AuditReceipt, event_id=self.event.event_id,
            durability=Durability.LEDGER_CONFIRMED, stored_at=AT, chain_version='v1',
            entry_ref='audit/ledger/1', sequence=1, entry_hash=HASH, checkpoint_ref=None)
        self.sink.append.return_value = confirmed
        self.assertIs(self.gateway.record(self.event, Durability.LEDGER_CONFIRMED), confirmed)
        self.sink.append.return_value = self.receipt
        result = self.gateway.record(self.event, Durability.LEDGER_CONFIRMED)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)

    def test_mismatched_receipts_fail_closed(self):
        for receipt in (None, {}, replace(self.receipt, event_id='other/event'),
                        replace(self.receipt, stored_at=AT - timedelta(seconds=1))):
            self.sink.append.return_value = receipt
            self.assertEqual(self.gateway.record(self.event, Durability.DURABLE).code,
                             ReasonCode.AUDIT_UNAVAILABLE)

    def test_raw_or_wrong_durability_never_reaches_sink(self):
        for event, durability in (({'detail': 'omitted'}, Durability.DURABLE),
                                  (self.event, 'durable')):
            self.assertEqual(self.gateway.record(event, durability).code, ReasonCode.INVALID_TYPE)
        self.sink.append.assert_not_called()

    def test_dto_rejects_arbitrary_detail(self):
        wire = self.event.to_wire()
        wire['detail'] = {'arbitrary': 'omitted'}
        with self.assertRaises(ContractViolation):
            SecurityEvent.from_wire(wire)

    def test_sink_exception_is_not_logged_or_retried(self):
        self.sink.append.side_effect = RuntimeError('never-activated-fixture-value')
        with patch('logging.Logger._log') as log:
            result = self.gateway.record(self.event, Durability.DURABLE)
        self.sink.append.assert_called_once()
        log.assert_not_called()
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertNotIn('never-activated-fixture-value', json.dumps(result.to_wire()))

    def test_typed_sink_error_keeps_code_not_sink_trace(self):
        self.sink.append.return_value = dto(ProtectionError, code=ReasonCode.IDEMPOTENCY_CONFLICT,
            retryable=False, trace_id='sink/private-reference')
        result = self.gateway.record(self.event, Durability.DURABLE)
        self.assertEqual(result.code, ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(result.trace_id, self.event.correlation_ref)

    def test_legacy_bridge_projects_only_server_ids(self):
        self.sink.append.side_effect = lambda event, durability: replace(
            self.receipt, event_id=event.event_id, durability=durability)
        with patch.object(bridge, '_binding', None):
            bridge.bind(audit=self.gateway, policy_binding=self.event.policy_binding,
                        clock=lambda: AT, event_id=lambda: 'legacy/1')
            bridge.record(category='never-activated-fixture-value', actor_id='private-user', object_id='private-id')
        event = self.sink.append.call_args.args[0]
        self.assertEqual(event.actor_ref, 'actor/unspecified')
        self.assertEqual(event.object_ref, 'legacy/event')
        self.assertNotIn('never-activated-fixture-value', json.dumps(event.to_wire()))
        self.assertNotIn('private-user', json.dumps(event.to_wire()))

    def test_legacy_bridge_raises_safe_error_instead_of_fallback(self):
        self.sink.append.return_value = dto(ProtectionError, code=ReasonCode.AUDIT_UNAVAILABLE,
                                          retryable=False, trace_id='fixture/failure')
        with patch.object(bridge, '_binding', None):
            bridge.bind(audit=self.gateway, policy_binding=self.event.policy_binding,
                        clock=lambda: AT, event_id=lambda: 'legacy/1')
            with self.assertRaises(ContractViolation):
                bridge.record(category='auth')
        self.sink.append.assert_called_once()

    def test_authenticate_has_no_audit_callback(self):
        crypto = CryptoService(keys=FakeKeys(), service_identity='service/audit',
            random_bytes=lambda size: bytes(size), environment=Environment.TEST, limits=BASELINE_LIMITS)
        with patch.object(AuditGateway, 'record') as record, patch('logging.Logger._log') as log:
            result = crypto.authenticate(b'bounded-metadata', examples()[ObjectContext],
                                         reference_key(KeyPurpose.AUDIT))
        self.assertIs(type(result), bytes)
        record.assert_not_called()
        log.assert_not_called()


class UnsafeRendering:
    def __str__(self):
        raise AssertionError('unsafe-rendering-called')


class AuditLoggingTests(unittest.TestCase):
    def test_message_args_exception_cached_text_stack_and_extra_are_dropped(self):
        value = 'never-activated-fixture-value'
        record = logging.LogRecord(value, logging.ERROR, value, 7, UnsafeRendering(),
            (UnsafeRendering(),), (RuntimeError, RuntimeError(value), None), value, value)
        record.exc_text = value
        record.__dict__.update(request={'Authorization': value}, arbitrary=UnsafeRendering(),
                               threadName=value, processName=value)
        output = SafeLogFormatter('%(name)s %(levelname)s %(message)s').format(record)
        self.assertEqual(output, 'application ERROR LOG_EXCEPTION_OMITTED')
        self.assertNotIn(value, json.dumps(record.__dict__))
        self.assertIsNone(record.exc_info)
        self.assertIsNone(record.stack_info)
        self.assertEqual(record.args, ())
        self.assertNotIn('request', record.__dict__)

    def test_only_fixed_reason_kind_and_bounded_counts_survive(self):
        record = logging.LogRecord('test', 20, '', 0, 'raw', (), None)
        record.__dict__.update(reason_code=ReasonCode.AUDIT_UNAVAILABLE,
            event_kind=EventKind.PROTECTION,
            counts={'processed': 3, 'bytes': 2**53, 'failed': True, 'unknown': -1, 'secret': 7})
        SafeLogFilter().filter(record)
        SafeLogFilter().filter(record)
        self.assertEqual(record.msg, 'AUDIT_UNAVAILABLE')
        self.assertEqual(record.event_kind, 'protection')
        self.assertEqual(record.counts, {'processed': 3})

    def test_unknown_reason_and_kind_are_not_rendered(self):
        record = logging.LogRecord('test', 20, '', 0, '%s', (UnsafeRendering(),), None)
        record.reason_code = UnsafeRendering()
        record.event_kind = UnsafeRendering()
        self.assertEqual(SafeLogFormatter().format(record), 'LOG_MESSAGE_OMITTED')
        self.assertEqual(record.reason_code, '')
        self.assertEqual(record.event_kind, '')

    def test_split_credentials_and_child_logger_cannot_bypass_handler(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.addFilter(SafeLogFilter())
        handler.setFormatter(SafeLogFormatter())
        parent = logging.getLogger('phase3-audit-test')
        child = parent.getChild('sdk')
        with patch.object(parent, 'handlers', [handler]), patch.object(parent, 'propagate', False), \
                patch.object(parent, 'level', logging.INFO), patch.object(child, 'level', logging.INFO):
            for chunk in ('Authorization: Bearer ', 'never-activated-', 'fixture-value'):
                child.info(chunk)
        self.assertEqual(output.getvalue(), 'LOG_MESSAGE_OMITTED\n' * 3)
