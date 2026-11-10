"""Report MACs authenticate owner bindings, not client success declarations."""
from dataclasses import replace
from datetime import timedelta
import os
import unittest
from unittest.mock import patch

from data_security.application.crypto_service import CryptoService
from data_security.application.reports import ReportAuthenticator
from data_security.contracts import (
    ActionPlan, BASELINE_LIMITS, ContractViolation, Environment, ExecutionBinding, KeyPurpose, KeyStatus,
    MaskReport, ObjectContext, Outcome, ProtectionError, ReasonCode, ReportProof, ScanState, SourceTrust,
    canonical_bytes, content_hash,
)
from data_security.tests.fixtures import AT, examples
from data_security.tests.phase2_fixtures import FakeKeys, reference_key


def report_with(report, **changes):
    values = dict(report.content(), **changes)
    return MaskReport(**values, report_hash=content_hash(values))


def plan_with(plan, **changes):
    values = dict(plan.content(), **changes)
    return ActionPlan(**values, plan_hash=content_hash(values), approval=None)


class ReportAuthenticationTests(unittest.TestCase):
    def setUp(self):
        values = examples()
        self.execution = values[ExecutionBinding]
        self.context = replace(values[ObjectContext], object_version=self.execution.asset_version,
                               authorization_ref=self.execution.authorization_id)
        plan = values[ActionPlan]
        source = replace(plan.source, source_trust=SourceTrust.SYNTHETIC,
            source_environment=self.execution.environment, source_domain=self.execution.domain_ref,
            provenance_ref='provenance/test', approval_basis_ref='approval/test', approval_basis_version='v1')
        self.plan = plan_with(plan, source=source)
        self.report = report_with(values[MaskReport], source=source, action_plan_hash=self.plan.plan_hash,
            ciphertext_hash='2' * 64,
            algorithm_versions=tuple(sorted({a.algorithm.algorithm.value + '/' + a.algorithm.version
                                             for a in self.plan.actions})))
        self.hashes = dict(input_hash=self.plan.input_hash, output_hash=self.report.output_hash,
                           ciphertext_hash=self.report.ciphertext_hash)
        self.now = AT + timedelta(seconds=1)
        self.keys = FakeKeys()
        self.crypto = CryptoService(keys=self.keys, service_identity='reports/test', random_bytes=os.urandom,
            environment=Environment.TEST, limits=BASELINE_LIMITS)
        self.key = reference_key(KeyPurpose.AUDIT)
        self.service = ReportAuthenticator(crypto=self.crypto, key=self.key, executor_ref=self.report.executor_ref,
                                          environment=Environment.TEST, clock=lambda: self.now)

    def issue(self):
        result = self.service.issue(self.report, self.execution, self.plan, self.context, **self.hashes)
        self.assertIsInstance(result, ReportProof)
        return result

    def verify(self, proof, **changes):
        arguments = dict(report=self.report, proof=proof, execution=self.execution,
                         plan=self.plan, context=self.context, **self.hashes)
        arguments.update(changes)
        return self.service.verify(**arguments)

    def denied(self, result, code=None):
        self.assertIsInstance(result, ProtectionError)
        if code is not None:
            self.assertEqual(result.code, code)

    def test_issue_wire_roundtrip_replay_and_verification(self):
        proof = self.issue()
        self.assertEqual(self.issue(), proof)
        decoded = ReportProof.from_json(canonical_bytes(proof))
        self.assertIs(self.verify(decoded), True)
        self.assertEqual(proof.execution_hash, content_hash(self.execution))
        self.assertEqual(proof.context_hash, content_hash(self.context))
        self.assertEqual(repr(proof), 'ReportProof(<redacted>)')
        self.assertNotIn(proof.authentication.hex(), repr(proof))

    def test_missing_proof_and_client_report_dictionary_are_denied(self):
        proof = self.issue()
        with patch.object(self.crypto, 'verify_authentication', wraps=self.crypto.verify_authentication) as mac:
            self.denied(self.verify(None), ReasonCode.REPORT_MISMATCH)
            self.denied(self.verify(proof, report=self.report.to_wire()), ReasonCode.REPORT_MISMATCH)
            self.denied(self.verify(proof, report=None), ReasonCode.REPORT_MISMATCH)
            mac.assert_not_called()

    def test_recomputed_report_and_proof_hashes_cannot_replace_mac(self):
        proof = self.issue()
        forged = report_with(self.report, hit_count=self.report.hit_count + 1)
        forged_proof = replace(proof, report_hash=forged.report_hash)
        self.denied(self.verify(forged_proof, report=forged), ReasonCode.REPORT_MISMATCH)
        self.denied(self.verify(replace(proof, authentication=bytes(32))), ReasonCode.REPORT_MISMATCH)
        self.assertIs(self.verify(proof), True)

    def test_every_expected_content_digest_is_checked(self):
        proof = self.issue()
        for field in self.hashes:
            self.denied(self.verify(proof, **{field: '3' * 64}), ReasonCode.REPORT_MISMATCH)
        for field in ('input_hash', 'output_hash', 'ciphertext_hash'):
            changed = report_with(self.report, **{field: '3' * 64})
            self.denied(self.verify(proof, report=changed), ReasonCode.REPORT_MISMATCH)
        self.denied(self.verify(proof, report=report_with(self.report, ciphertext_hash=None)),
                    ReasonCode.REPORT_MISMATCH)

    def test_execution_identity_scope_policy_and_quantity_cannot_be_rebound(self):
        proof = self.issue()
        changes = [dict(request_fingerprint='4' * 64), dict(quantity=self.execution.quantity + 1),
            dict(expires_at=self.execution.expires_at - timedelta(seconds=1)),
            dict(scope=replace(self.execution.scope, sheets=(replace(self.execution.scope.sheets[0],
                                                        includes_header=False),))),
            dict(policy_binding=replace(self.execution.policy_binding, risk_hash='4' * 64))]
        changes += [{name: 'changed/reference'} for name in ('idempotency_key', 'request_id', 'authorization_id',
            'decision_id', 'asset_version', 'execution_id', 'reservation_id', 'subject_ref', 'domain_ref')]
        for change in changes:
            self.denied(self.verify(proof, execution=replace(self.execution, **change)))

    def test_object_environment_field_version_and_authorization_are_bound(self):
        proof = self.issue()
        for changes in ({'project_ref': 'project/other'}, {'environment': Environment.EVALUATION},
                        {'object_uuid': '00000000-0000-4000-8000-000000000002'},
                        {'object_version': 'other/version'}, {'field_ref': 'other/field'},
                        {'authorization_ref': 'authorization/other'}):
            self.denied(self.verify(proof, context=replace(self.context, **changes)))

    def test_source_plan_and_target_actions_are_not_interchangeable(self):
        proof = self.issue()
        for source in (replace(self.plan.source, source_record_version='v2'),
                       replace(self.plan.source, scope_hash='sha256:' + '5' * 64)
                       if self.plan.source.scope_hash.startswith('sha256:') else
                       replace(self.plan.source, scope_hash='5' * 64)):
            changed = plan_with(self.plan, source=source)
            self.denied(self.verify(proof, plan=changed), ReasonCode.REPORT_MISMATCH)
        changed = plan_with(self.plan, adapter_version='adapter/other')
        self.denied(self.verify(proof, plan=changed), ReasonCode.REPORT_MISMATCH)
        changed_report = report_with(self.report, executor_ref='executor/other')
        self.denied(self.verify(proof, report=changed_report), ReasonCode.REPORT_MISMATCH)
        self.denied(self.verify(proof, report=report_with(self.report, algorithm_versions=('replace/other',))),
                    ReasonCode.REPORT_MISMATCH)

    def test_failed_partial_unresolved_and_unscanned_reports_do_not_authorize(self):
        proof = self.issue()
        failed = report_with(self.report, outcome=Outcome.FAILED, output_hash=None, ciphertext_hash=None,
            rescan_state=ScanState.UNSCANNED)
        self.denied(self.verify(proof, report=failed))
        partial = replace(self.report.rescan_coverage, total=self.report.rescan_coverage.total + 1, excluded=1)
        self.denied(self.verify(proof, report=report_with(self.report, rescan_coverage=partial)),
                    ReasonCode.SCOPE_INCOMPLETE)
        # Successful reports with an unscanned range never cross the M0 boundary.
        with self.assertRaises(ContractViolation):
            report_with(self.report, rescan_coverage=replace(self.report.rescan_coverage,
                processed=self.report.rescan_coverage.processed - 1, unscanned=1))
        from data_security.contracts import Unresolved
        unresolved = Unresolved(schema_version=Unresolved.SCHEMA, location=None,
                                reason=ReasonCode.UNSUPPORTED_SCOPE, source_ref='source/unresolved')
        self.denied(self.verify(proof, plan=plan_with(self.plan, unresolved=(unresolved,))))

    def test_current_time_rechecks_execution_plan_and_report_chronology(self):
        proof = self.issue()
        self.now = self.execution.expires_at
        self.denied(self.verify(proof), ReasonCode.AUTHORIZATION_EXPIRED)
        self.now = AT - timedelta(seconds=1)
        self.denied(self.verify(proof), ReasonCode.AUTHORIZATION_EXPIRED)
        self.now = AT + timedelta(seconds=1)
        expired_plan = plan_with(self.plan, expires_at=self.now)
        expired_report = report_with(self.report, action_plan_hash=expired_plan.plan_hash)
        self.denied(self.service.issue(expired_report, self.execution, expired_plan, self.context, **self.hashes),
                    ReasonCode.AUTHORIZATION_EXPIRED)

    def test_unverified_and_production_source_remain_closed(self):
        proof = self.issue()
        for source in (replace(self.plan.source, source_trust=SourceTrust.UNVERIFIED),
                       replace(self.plan.source, source_trust=SourceTrust.PRODUCTION),
                       replace(self.plan.source, source_environment='production'),
                       replace(self.plan.source, approval_basis_ref=None, approval_basis_version=None)):
            self.denied(self.verify(proof, plan=plan_with(self.plan, source=source)), ReasonCode.SOURCE_NOT_APPROVED)
        with self.assertRaises(ContractViolation):
            ReportAuthenticator(crypto=self.crypto, key=self.key, executor_ref='executor/test',
                                environment=Environment.PRODUCTION, clock=lambda: self.now)

    def test_key_unavailable_wrong_key_and_readonly_issuance_are_denied(self):
        proof = self.issue()
        self.keys.error = ReasonCode.KEY_UNAVAILABLE
        self.denied(self.verify(proof), ReasonCode.KEY_UNAVAILABLE)
        self.keys.error = None
        other = reference_key(KeyPurpose.DATA)
        for key in (other, replace(self.key, status=KeyStatus.RETIRED)):
            with self.assertRaises(ContractViolation):
                ReportAuthenticator(crypto=self.crypto, key=key, executor_ref='executor/test',
                                    environment=Environment.TEST, clock=lambda: self.now)
        self.denied(self.verify(replace(proof, key=replace(self.key, key_ref='audit-auth/v2', version='v2'))),
                    ReasonCode.REPORT_MISMATCH)

    def test_report_mac_cannot_be_replaced_by_general_metadata_authentication(self):
        proof = self.issue()
        data = canonical_bytes({'domain': 'ds.mask-report-auth.v1', 'binding': proof.content()})
        other_scope = self.crypto.authenticate(data, self.context, self.key)
        self.denied(self.verify(replace(proof, authentication=other_scope)), ReasonCode.REPORT_MISMATCH)
        with patch.object(self.crypto, 'verify_authentication', return_value=b'short'):
            self.denied(self.verify(proof), ReasonCode.KEY_UNAVAILABLE)
        with patch.object(self.crypto, 'authenticate', return_value=b'short'):
            self.denied(self.service.issue(self.report, self.execution, self.plan, self.context, **self.hashes),
                        ReasonCode.KEY_UNAVAILABLE)

    def test_retained_readonly_key_verifies_original_proof_without_issuing_or_extending_expiry(self):
        proof = self.issue()
        old = replace(self.key, status=KeyStatus.READ_ONLY)
        self.service = ReportAuthenticator(crypto=self.crypto, key=old, executor_ref=self.report.executor_ref,
                                          environment=Environment.TEST, clock=lambda: self.now)
        with patch.object(self.crypto, 'authenticate', side_effect=AssertionError('readonly signing')):
            self.assertIs(self.verify(proof), True)
            self.assertIs(self.keys.calls[-1][0].status, KeyStatus.READ_ONLY)
            self.denied(self.service.issue(self.report, self.execution, self.plan, self.context, **self.hashes),
                        ReasonCode.KEY_UNAVAILABLE)
        self.denied(self.verify(replace(proof, key=old)), ReasonCode.REPORT_MISMATCH)
        self.now = self.execution.expires_at
        self.denied(self.verify(proof), ReasonCode.AUTHORIZATION_EXPIRED)
