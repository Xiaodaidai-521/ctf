"""Canary alerts through the sole gateway and real isolated authenticated ledger."""
from dataclasses import replace
import io
import json
import logging
from unittest.mock import Mock, patch

import requests

from django.test import TransactionTestCase
from django.utils import timezone

from data_security.adapters.persistence.audit import DjangoAuditSink
from data_security.application.audit_gateway import AuditGateway
from data_security.application.canary import CanaryTools
from data_security.contracts import (
    BASELINE_LIMITS, CanarySeed, Environment, Outlet, PolicyBinding, ProtectionContext,
    AIResponse, EmbeddingResult, Purpose, ReasonCode, SecurityEventV2, canonical_bytes,
)
from data_security.tests.fixtures import examples
from data_security.tests.test_phase6_canary import text
from .models import AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord
from .test_phase6_authenticated_chain import AuditChainFixture


class CanaryChainTests(AuditChainFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.seed = examples()[CanarySeed]
        self.owner = replace(examples()[ProtectionContext], object_ref=self.seed.target_ref,
            object_version=self.seed.target_version, outlet=Outlet.AUDIT, purpose=Purpose.SECURITY_AUDIT)
        self.packets = []
        def plant(seed, packet, context):
            self.packets.append(packet)
            return seed
        self.tools = CanaryTools(seeds=(self.seed,), environment=Environment.TEST, domain=self.seed.domain,
            limits=BASELINE_LIMITS, policy_binding=examples()[PolicyBinding],
            authorize=lambda operation, context, seed: context, plant_target=plant, audit=self.gateway,
            clock=timezone.now, event_id=lambda: 'canary/pg/' + str(SecurityAuditRecord.objects.count() + 1))
        self.assertEqual(self.tools.plant(seed_id=self.seed.seed_id, context=self.owner), self.seed)
        self.values = self.packets[0].tree.to_value()['values']

    def test_each_egress_label_has_authenticated_metadata_and_no_literal_with_clean_control(self):
        for outlet in (Outlet.MODEL, Outlet.EMBEDDING, Outlet.LOG, Outlet.EXPORT):
            context = replace(self.owner, outlet=outlet, trace_id='synthetic/' + outlet.value)
            self.assertEqual(self.tools.check(payload=text('[EMAIL] [IPV4] [CARD]'), context=context), ())
            receipt, = self.tools.check(payload=text(' '.join(self.values.values())), context=context)
            self.assertEqual(receipt.chain_version, 'ds.audit.v2')
            self.assertEqual(self.sink.verify('ds.audit.v2'), receipt)
            row = SecurityAuditRecord.objects.get(event_id=receipt.event_id)
            event = SecurityEventV2.from_wire(row.event)
            self.assertEqual(event.counts, (('hit', 3),))
            self.assertIn('outlet/' + outlet.value, event.algorithm_versions)
            self.assertEqual(event.correlation_ref, context.trace_id)
            for literal in self.values.values():
                self.assertNotIn(literal.encode(), canonical_bytes(event))
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 4)
        self.assertEqual(SecurityAuditRecord.objects.count(), 4)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_actual_model_and_embedding_boundaries_record_authenticated_alerts_before_send(self):
        from data_security.tests import test_phase3_official as official
        fixture = official.OfficialTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        tools = CanaryTools(seeds=(replace(self.seed, environment=fixture.context.environment,
            domain=fixture.context.domain),), environment=fixture.context.environment, domain=fixture.context.domain,
            limits=BASELINE_LIMITS, policy_binding=fixture.binding,
            authorize=lambda operation, context, seed: context, plant_target=Mock(), audit=self.gateway,
            clock=timezone.now, event_id=self.tools.event_id)
        for embedding in (False, True):
            adapter = fixture.adapter('qwen' if embedding else 'deepseek')
            adapter.canary = tools
            context = replace(fixture.context, outlet=Outlet.EMBEDDING if embedding else Outlet.MODEL)
            body = {'input': list(self.values.values())} if embedding else {
                'messages': [{'role': 'user', 'content': ' '.join(self.values.values())}]}
            request = fixture.request(adapter.endpoint_ref, body, embedding)
            method = adapter.embed if embedding else adapter.chat
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps({'data': [{'index': n, 'embedding': [0.1]} for n in range(3)]}
                if embedding else {'choices': [{'message': {'content': 'safe'}}]}).encode()
            response._content_consumed = True
            with patch.object(requests.Session, 'send', return_value=response) as send:
                result = method(request, context, fixture.binding)
                self.assertIsInstance(result, EmbeddingResult if embedding else AIResponse)
                self.assertEqual(send.call_count, 1)
            before = AuthenticatedAuditEntry.objects.count()
            with patch.object(adapter, '_protect', side_effect=lambda payload, *_: payload), \
                    patch.object(requests.Session, 'send') as send, patch.object(fixture.keys, 'resolve') as resolve:
                result = method(request, context, fixture.binding)
                self.assertEqual(result.code, ReasonCode.SCOPE_INCOMPLETE)
                send.assert_not_called()
                resolve.assert_not_called()
            verified = self.sink.verify('ds.audit.v2')
            self.assertEqual(verified.sequence, before + 1)
            event = SecurityEventV2.from_wire(SecurityAuditRecord.objects.get(event_id=verified.event_id).event)
            self.assertEqual(event.counts, (('hit', 3),))
            self.assertIn('outlet/' + context.outlet.value, event.algorithm_versions)
            for literal in self.values.values():
                self.assertFalse(literal.encode() in canonical_bytes(event))
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_actual_log_stream_suppresses_literal_after_authenticated_alert(self):
        from data_security.adapters.django.logging import SafeLogFormatter
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.setFormatter(SafeLogFormatter(canary=self.tools,
            canary_context=replace(self.owner, outlet=Outlet.LOG), limits=BASELINE_LIMITS))
        literal = ' '.join(self.values.values())
        handler.handle(logging.LogRecord('test', 20, '', 0, literal, (), None))
        self.assertEqual(output.getvalue(), 'LOG_MESSAGE_OMITTED\n')
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        with patch.object(logging.Formatter, 'format', return_value=literal):
            handler.handle(logging.LogRecord('test', 20, '', 0, 'safe', (), None))
        self.assertEqual(output.getvalue(), 'LOG_MESSAGE_OMITTED\nLOG_CANARY_BLOCKED\n')
        verified = self.sink.verify('ds.audit.v2')
        self.assertEqual(verified.sequence, 1)
        event = SecurityEventV2.from_wire(SecurityAuditRecord.objects.get(event_id=verified.event_id).event)
        self.assertEqual(event.counts, (('hit', 3),))
        self.assertIn('outlet/log', event.algorithm_versions)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_actual_serialized_export_records_authenticated_alert_before_candidate_write(self):
        from data_security.adapters.tabular.codec import TableCodec
        from data_security.application.table_reports import ReportCandidate
        from data_security.tests import test_phase6_table_reports as tables
        fixture = tables.TableReportTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.executor.canary = CanaryTools(seeds=(replace(self.seed, domain=fixture.execution.domain_ref),),
            environment=Environment.TEST, domain=fixture.execution.domain_ref, limits=BASELINE_LIMITS,
            policy_binding=fixture.plan.policy_binding, authorize=lambda operation, context, seed: context,
            plant_target=Mock(), audit=self.gateway, clock=timezone.now, event_id=self.tools.event_id)
        context = replace(self.owner, outlet=Outlet.EXPORT, purpose=Purpose.DELIVERY,
            actor_ref=fixture.execution.subject_ref, domain=fixture.execution.domain_ref,
            authorization_ref=fixture.execution.authorization_id, object_ref=fixture.context.object_uuid,
            object_version=fixture.context.object_version, trace_id=fixture.execution.execution_id)
        result = fixture.executor.prepare(fixture.payload, fixture.plan, fixture.execution, fixture.context,
                                          canary_context=context)
        self.assertIsInstance(result, ReportCandidate)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        before = list(fixture.store.calls)
        real = TableCodec.serialize
        def inject(codec, snapshot, limits):
            output = real(codec, snapshot, limits)
            return replace(output, binary=output.binary.replace(b'[EMAIL]', ' '.join(self.values.values()).encode(), 1))
        with patch.object(TableCodec, 'serialize', inject), patch.object(fixture.crypto, 'seal') as seal:
            result = fixture.executor.prepare(fixture.payload, fixture.plan, fixture.execution, fixture.context,
                                              canary_context=context)
            self.assertEqual(result.code, ReasonCode.SCOPE_INCOMPLETE)
            seal.assert_not_called()
        self.assertEqual(fixture.store.calls, before)
        verified = self.sink.verify('ds.audit.v2')
        self.assertEqual(verified.sequence, 1)
        event = SecurityEventV2.from_wire(SecurityAuditRecord.objects.get(event_id=verified.event_id).event)
        self.assertEqual(event.counts, (('hit', 3),))
        self.assertEqual(event.correlation_ref, fixture.execution.execution_id)
        self.assertIn('outlet/export', event.algorithm_versions)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_unconfigured_or_unavailable_audit_key_never_creates_a_legacy_success(self):
        context = replace(self.owner, outlet=Outlet.EXPORT)
        payload = text(self.values['email_address'])
        self.tools.audit = AuditGateway(sink=DjangoAuditSink(clock=timezone.now))
        self.assertEqual(self.tools.check(payload=payload, context=context).code, ReasonCode.AUDIT_UNAVAILABLE)
        self.tools.audit = self.gateway
        self.crypto.keys.error = ReasonCode.KEY_UNAVAILABLE
        self.assertEqual(self.tools.check(payload=payload, context=context).code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)
