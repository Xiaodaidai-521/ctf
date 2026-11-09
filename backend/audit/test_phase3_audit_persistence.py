"""Run only on the approved isolated PostgreSQL through the safe Django runner."""
from dataclasses import replace
import itertools
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import DatabaseError
from django.test import TestCase
from django.utils import timezone

from data_security.application.audit_gateway import AuditGateway
from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.contracts import (AuditReceipt, ContractViolation, Durability, Outcome,
                                     ProtectionError, ReasonCode, SecurityEvent)
from data_security.tests.fixtures import examples
from export_risk.decisions import outbox
from export_risk.models import EventOutbox
from . import bridge
from .middleware import AuditMiddleware
from .models import AIAuditLog, AuditEvent, AuditLedgerEntry, SecurityAuditRecord
from .services import AuditLedgerService


class Phase3AuditPersistenceTests(TestCase):
    def setUp(self):
        self.event = examples()[SecurityEvent]
        self.sink = DjangoAuditSink(clock=timezone.now)
        self.gateway = AuditGateway(sink=self.sink)
        for module in (bridge, outbox):
            binding = patch.object(module, '_binding', None)
            binding.start()
            self.addCleanup(binding.stop)
        ids = itertools.count(1)
        bridge.bind(audit=self.gateway, policy_binding=self.event.policy_binding,
                    clock=timezone.now, event_id=lambda: f'legacy/{next(ids)}')
        outbox.bind(audit=self.gateway, policy_binding=self.event.policy_binding, clock=timezone.now)

    def test_durable_deduplicates_without_claiming_a_chain_entry(self):
        first = self.gateway.record(self.event, Durability.DURABLE)
        second = self.gateway.record(self.event, Durability.DURABLE)
        self.assertEqual(first, second)
        self.assertEqual(first.durability, Durability.DURABLE)
        self.assertIsNone(first.entry_hash)
        self.assertIsNone(first.sequence)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), 1)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_confirm_upgrade_and_replay_append_only_once(self):
        durable = self.gateway.record(self.event, Durability.DURABLE)
        confirmed = self.gateway.record(self.event, Durability.LEDGER_CONFIRMED)
        replayed = self.gateway.record(self.event, Durability.LEDGER_CONFIRMED)
        self.assertEqual(confirmed, replayed)
        self.assertEqual(confirmed.durability, Durability.LEDGER_CONFIRMED)
        self.assertEqual(confirmed.chain_version, 'v1')
        self.assertIsNone(confirmed.checkpoint_ref)
        self.assertEqual(self.gateway.record(self.event, Durability.DURABLE), durable)
        self.assertEqual(AuditLedgerEntry.objects.count(), 1)
        self.assertTrue(AuditLedgerService.verify_chain().is_valid)

    def test_event_id_cannot_be_reused_for_changed_metadata(self):
        self.gateway.record(self.event, Durability.DURABLE)
        result = self.gateway.record(replace(self.event, outcome=Outcome.FAILED),
                                     Durability.LEDGER_CONFIRMED)
        self.assertEqual(result.code, ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), 1)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_sink_calls_only_private_writer_and_never_gateway(self):
        with patch.object(AuditLedgerService, 'append_entry') as legacy, \
                patch.object(AuditGateway, 'record') as public:
            receipt = self.sink.append(self.event, Durability.LEDGER_CONFIRMED)
        self.assertIs(type(receipt), AuditReceipt)
        legacy.assert_not_called()
        public.assert_not_called()

    def test_sink_fault_rolls_back_and_returns_safe_error_without_recursion(self):
        with patch.object(AuditLedgerService, '_append_entry',
                          side_effect=DatabaseError('never-activated-fixture-value')) as writer, \
                patch('logging.Logger._log') as log:
            result = self.gateway.record(self.event, Durability.LEDGER_CONFIRMED)
        self.assertEqual(result.code, ReasonCode.AUDIT_UNAVAILABLE)
        writer.assert_called_once()
        log.assert_not_called()
        self.assertEqual(AuditEvent.objects.count(), 0)
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_three_bound_legacy_entries_drop_all_original_text(self):
        value = 'never-activated-fixture-value'
        request = SimpleNamespace(META={'HTTP_USER_AGENT': value, 'REMOTE_ADDR': '192.0.2.7'})
        event = AuditEvent.log(value, value, detail={'token': value}, request=request)
        ai = AIAuditLog.log_ai_call(None, value, value, value, value,
                                   mode=value, error_message=value, success=False, request=request)
        ledger = AuditLedgerService.append_entry(event_category=value, payload={'detail': value},
                                                 object_type=value, object_id=value)
        self.assertIs(type(event), AuditEvent)
        self.assertIs(type(ai), AIAuditLog)
        self.assertIs(type(ledger), AuditLedgerEntry)
        self.assertNotIn(value, json.dumps(list(SecurityAuditRecord.objects.values('event'))))
        self.assertNotIn(value, json.dumps(list(AuditEvent.objects.values('summary', 'detail', 'user_agent'))))
        self.assertNotIn(value, json.dumps(list(AuditLedgerEntry.objects.values('payload', 'object_type', 'object_id'))))
        self.assertEqual(ai.user_message, '')
        self.assertEqual(ai.ai_response, '')
        self.assertEqual(ai.error_message, 'PROVIDER_UNAVAILABLE')
        self.assertIsNone(event.ip_address)
        self.assertIsNone(ai.ip_address)

    def test_unbound_legacy_path_retains_baseline_and_old_hash_algorithm(self):
        with patch.object(bridge, '_binding', None):
            event = AuditEvent.log('auth', 'legacy summary', detail={'step': 1})
            ai = AIAuditLog.log_ai_call(None, 'legacy', 'legacy', 'legacy input')
            ledger = AuditLedgerService.append_entry(event_category='auth', payload={'step': 1})
        self.assertEqual(event.detail, {'step': 1})
        self.assertEqual(ai.user_message, 'legacy input')
        self.assertEqual(ledger.payload, {'step': 1})
        self.gateway.record(self.event, Durability.LEDGER_CONFIRMED)
        ledger.refresh_from_db()
        self.assertEqual(ledger.payload, {'step': 1})
        self.assertTrue(AuditLedgerService.verify_chain().is_valid)

    def test_legacy_entry_does_not_fallback_when_gateway_fails(self):
        with patch.object(self.sink, 'append', side_effect=DatabaseError('omitted')):
            with self.assertRaises(ContractViolation):
                AuditEvent.log('auth', 'omitted')
            with self.assertRaises(ContractViolation):
                AIAuditLog.log_ai_call(None, 'omitted', 'omitted', 'omitted')
            with self.assertRaises(ContractViolation):
                AuditLedgerService.append_entry(event_category='auth', payload={})
        self.assertEqual(AuditEvent.objects.count(), 0)
        self.assertEqual(AIAuditLog.objects.count(), 0)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_relay_requests_confirmed_without_reenqueuing_and_deduplicates_replays(self):
        row = outbox.enqueue('export/event-1', 'decision.issued', {'detail': 'never-activated-fixture-value'})
        duplicate = outbox.enqueue('export/event-1', 'decision.issued', {})
        self.assertEqual(row.pk, duplicate.pk)
        self.assertNotIn('detail', row.payload)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)
        with patch.object(outbox, 'enqueue', side_effect=AssertionError('recursive-enqueue')):
            self.assertEqual(outbox.relay_pending(), 1)
            self.assertEqual(outbox.relay_pending(), 0)
            EventOutbox.objects.filter(pk=row.pk).update(status='pending')
            self.assertEqual(outbox.relay_pending(), 1)
        row.refresh_from_db()
        self.assertEqual(row.status, 'sent')
        self.assertEqual(row.ledger_hash, AuditLedgerEntry.objects.get().current_hash)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(EventOutbox.objects.count(), 1)

    def test_relay_rejects_durable_receipt_and_leaves_pending(self):
        row = outbox.enqueue(self.event.event_id, 'decision.issued', {})
        port = Mock()
        port.record.return_value = examples()[AuditReceipt]
        outbox.bind(audit=port, policy_binding=self.event.policy_binding, clock=timezone.now)
        with self.assertRaises(ContractViolation):
            outbox.relay_pending()
        row.refresh_from_db()
        self.assertEqual(row.status, 'pending')
        self.assertEqual(row.ledger_hash, '')
        self.assertEqual(port.record.call_args.args[1], Durability.LEDGER_CONFIRMED)

    def test_relay_fault_leaves_outbox_and_ledger_atomic(self):
        row = outbox.enqueue('export/event-1', 'execution.authorized', {})
        with patch.object(AuditLedgerService, '_append_entry', side_effect=DatabaseError('omitted')):
            with self.assertRaises(ContractViolation):
                outbox.relay_pending()
        row.refresh_from_db()
        self.assertEqual(row.status, 'pending')
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_old_pending_payload_is_projected_before_relay(self):
        with patch.object(outbox, '_binding', None):
            row = outbox.enqueue('export/event-1', 'decision.issued', {'detail': 'never-activated-fixture-value'})
        self.assertEqual(outbox.relay_pending(), 1)
        row.refresh_from_db()
        self.assertNotIn('detail', row.payload)
        self.assertEqual(row.payload['schema_version'], SecurityEvent.SCHEMA)
        self.assertEqual(row.payload, AuditLedgerEntry.objects.get().payload)

    def test_verify_v1_and_explicitly_reject_checkpoint_or_new_chain(self):
        self.gateway.record(self.event, Durability.LEDGER_CONFIRMED)
        self.assertEqual(self.sink.verify('v1').chain_version, 'v1')
        self.assertEqual(self.sink.verify('ds.audit.v2').code, ReasonCode.UNSUPPORTED_FORMAT)
        self.assertEqual(self.sink.checkpoint('v1').code, ReasonCode.UNSUPPORTED_FORMAT)
        AuditLedgerEntry.objects.update(payload={'tampered': True})
        self.assertEqual(self.sink.verify('v1').code, ReasonCode.AUDIT_UNAVAILABLE)

    def test_middleware_never_formats_exception_or_logs_sink_failure_text(self):
        class UnsafeException(Exception):
            def __str__(self):
                raise AssertionError('exception-was-rendered')
        middleware = AuditMiddleware(lambda request: None)
        with patch.object(AuditEvent, 'log', side_effect=UnsafeException()) as write, \
                patch('audit.middleware.logger.error') as emergency:
            middleware.process_exception(SimpleNamespace(path='/fixture'), UnsafeException())
        self.assertEqual(write.call_args.kwargs['summary'], 'REQUEST_EXCEPTION')
        self.assertEqual(emergency.call_args.args, ('AUDIT_UNAVAILABLE',))
