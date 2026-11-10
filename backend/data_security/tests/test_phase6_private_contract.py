"""Stateful in-memory PrivateStore contract and real report preparation consumers."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import os
from unittest import TestCase
from unittest.mock import patch

from data_security.adapters.tabular.codec import TableCodec
from data_security.application.crypto_service import CryptoService
from data_security.application.reports import ReportAuthenticator
from data_security.application.table_reports import ReportCandidate, TableReportExecutor
from data_security.contracts import (
    BASELINE_LIMITS, CipherEnvelope, Environment, ExecutionBinding, KeyPurpose,
    MediaType, ObjectContext, ProtectionError, ReasonCode,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key
from data_security.tests.private_store_contract import PrivateStoreContract
from data_security.tests.private_store_memory import MemoryPrivateStore
from data_security.tests.test_phase5_codec import binary
from data_security.tests.test_phase5_pipeline import pipeline_fixture
from data_security.tests.test_source_plans import AT


class MemoryPrivateStoreContractTests(PrivateStoreContract, TestCase):
    def setUp(self):
        self.records, self.blobs = {}, {}
        super().setUp()

    def make_store(self):
        return MemoryPrivateStore(records=self.records, blobs=self.blobs,
                                  crypto=self.crypto, environment=Environment.TEST)

    def blob(self, stored):
        return self.blobs[stored.object_ref]

    def replace_blob(self, stored, encoded):
        self.blobs[stored.object_ref] = encoded

    def remove_blob(self, stored):
        del self.blobs[stored.object_ref]

    def remove_record(self, stored):
        del self.records[stored.object_ref]

    def resources(self):
        return len(self.records), len(self.blobs), sum(map(len, self.blobs.values()))


class MemoryPrivateReportTests(TestCase):
    def setUp(self):
        self.records, self.blobs = {}, {}
        self.crypto = CryptoService(keys=FakeKeys(), service_identity='private-contract/report',
            random_bytes=os.urandom, environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.store = MemoryPrivateStore(records=self.records, blobs=self.blobs,
                                       crypto=self.crypto, environment=Environment.TEST)
        _, self.plan, self.expected, content = pipeline_fixture('mainline', 'csv')
        self.payload = binary(content, MediaType.CSV)
        self.execution = replace(examples()[ExecutionBinding], asset_version=self.plan.asset_version,
            policy_binding=self.plan.policy_binding, scope=self.plan.scope, environment='test',
            domain_ref=self.plan.source.source_domain, expires_at=self.plan.expires_at)
        self.context = replace(examples()[ObjectContext], object_version=self.plan.asset_version,
                               authorization_ref=self.execution.authorization_id)
        self.auth = ReportAuthenticator(crypto=self.crypto, key=reference_key(KeyPurpose.AUDIT),
            executor_ref='executor/test', environment=Environment.TEST, clock=lambda: AT + timedelta(seconds=1))
        self.executor = TableReportExecutor(codec_factory=TableCodec, crypto=self.crypto,
            data_key=reference_key(), store=self.store, authenticator=self.auth,
            limits=BASELINE_LIMITS, clock=lambda: AT + timedelta(seconds=1))

    def test_real_preparation_leaves_verified_ciphertext_bound_to_report_but_unreadable(self):
        result = self.executor.prepare(self.payload, self.plan, self.execution, self.context)
        self.assertIs(type(result), ReportCandidate)
        self.assertEqual(result.stored.state, 'verified')
        encoded = self.blobs[result.stored.object_ref]
        self.assertEqual(result.report.ciphertext_hash, hashlib.sha256(encoded).hexdigest())
        envelope = CipherEnvelope.from_json(encoded)
        output = self.crypto.open(envelope, self.context, envelope.key)
        self.assertEqual(output.binary, self.expected)
        self.assertIs(self.auth.verify(result.report, result.proof, self.execution, self.plan, self.context,
            input_hash=hashlib.sha256(self.payload.binary).hexdigest(),
            output_hash=hashlib.sha256(output.binary).hexdigest(),
            ciphertext_hash=hashlib.sha256(encoded).hexdigest()), True)
        denied = self.store.read(replace(result.stored, state='published'), self.context)
        self.assertIs(type(denied), ProtectionError)
        self.assertEqual(denied.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual((len(self.records), len(self.blobs)), (1, 1))
        self.assertNotIn(self.payload.binary, encoded)
        self.assertNotIn(self.expected, encoded)

    def test_mutation_between_write_and_verify_cannot_issue_a_report(self):
        write = self.store.write_candidate
        def corrupt(envelope, context):
            candidate = write(envelope, context)
            self.blobs[candidate.object_ref] = self.blobs[candidate.object_ref][:-1]
            return candidate
        with patch.object(self.store, 'write_candidate', side_effect=corrupt), \
                patch.object(self.auth, 'issue', wraps=self.auth.issue) as issue:
            result = self.executor.prepare(self.payload, self.plan, self.execution, self.context)
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, ReasonCode.CIPHERTEXT_INVALID)
        issue.assert_not_called()
        self.assertEqual((len(self.records), len(self.blobs)), (1, 1))
        _, candidate = next(iter(self.records.values()))
        self.assertEqual(candidate.state, 'candidate')
        self.assertEqual(self.store.publish(candidate, self.context).code, ReasonCode.AUTHORIZATION_DENIED)
