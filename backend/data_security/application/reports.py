"""Internal report authentication, not a client report-signing endpoint.

The trusted executor supplies issue(); delivery loads the report and all expected
bindings from owner records before verify(). A hash, DTO or MAC alone is not a
fresh authorization, a quota check, or proof of a completed network transfer.
"""
from dataclasses import replace

from data_security.contracts import (
    ContractViolation, Environment, KeyPurpose, KeyStatus, MaskReport, Outcome,
    ProtectionError, ReasonCode, ReportProof, ScanState, SourceTrust, canonical_bytes, content_hash,
)
from data_security.contracts.schema import digest, reference, require, utc


class ReportAuthenticator:
    def __init__(self, *, crypto, key, executor_ref, environment, clock):
        require(type(environment) is Environment and environment is not Environment.PRODUCTION,
                ReasonCode.SOURCE_NOT_APPROVED)
        require(key.purpose is KeyPurpose.AUDIT and key.status in (KeyStatus.ACTIVE, KeyStatus.READ_ONLY),
                ReasonCode.KEY_UNAVAILABLE)
        reference(executor_ref)
        self.crypto, self.key, self.executor_ref = crypto, key, executor_ref
        self.environment, self.clock = environment, clock

    def issue(self, report, execution, plan, context, *, input_hash, output_hash, ciphertext_hash):
        """Only the trusted executor may call this after scanning and verifying its candidate."""
        return self._run(report, execution, plan, context, input_hash, output_hash, ciphertext_hash)

    def verify(self, report, proof, execution, plan, context, *, input_hash, output_hash, ciphertext_hash):
        return self._run(report, execution, plan, context, input_hash, output_hash, ciphertext_hash,
                         proof=proof, verifying=True)

    def _run(self, report, execution, plan, context, input_hash, output_hash, ciphertext_hash,
             *, proof=None, verifying=False):
        try:
            require(type(report) is MaskReport, ReasonCode.REPORT_MISMATCH)
            if verifying:
                require(type(proof) is ReportProof, ReasonCode.REPORT_MISMATCH)
            else:
                require(self.key.status is KeyStatus.ACTIVE, ReasonCode.KEY_UNAVAILABLE)
            for value in (input_hash, output_hash, ciphertext_hash):
                digest(value)
            require(execution.environment == self.environment.value and context.environment is self.environment,
                    ReasonCode.SOURCE_NOT_APPROVED)
            require(plan.source.source_trust is SourceTrust.SYNTHETIC and
                    plan.source.source_environment == execution.environment and
                    plan.source.source_domain == execution.domain_ref and
                    plan.source.provenance_ref is not None and plan.source.approval_basis_ref is not None,
                    ReasonCode.SOURCE_NOT_APPROVED)
            require((plan.asset_version, plan.policy_binding, plan.scope) ==
                    (execution.asset_version, execution.policy_binding, execution.scope), ReasonCode.REPORT_MISMATCH)
            require(context.authorization_ref == execution.authorization_id and
                    context.object_version == execution.asset_version, ReasonCode.REPORT_MISMATCH)
            require((report.execution_id, report.executor_ref, report.asset_version, report.source,
                     report.action_plan_hash, report.policy_binding) ==
                    (execution.execution_id, self.executor_ref, execution.asset_version, plan.source,
                     plan.plan_hash, execution.policy_binding), ReasonCode.REPORT_MISMATCH)
            require(report.input_hash == plan.input_hash == input_hash and report.output_hash == output_hash and
                    report.ciphertext_hash == ciphertext_hash, ReasonCode.REPORT_MISMATCH)
            algorithms = tuple(sorted({a.algorithm.algorithm.value + '/' + a.algorithm.version for a in plan.actions}))
            require(report.algorithm_versions == algorithms, ReasonCode.REPORT_MISMATCH)
            require(not plan.unresolved and not report.unresolved and report.outcome is Outcome.SUCCEEDED and
                    report.rescan_state is ScanState.COMPLETE, ReasonCode.SCOPE_INCOMPLETE)
            require(all(c.failed == c.unknown == c.unscanned == 0 and c.processed == c.eligible
                        for c in (report.coverage, report.rescan_coverage)) and
                    report.rescan_coverage.excluded == 0, ReasonCode.SCOPE_INCOMPLETE)
            now = self.clock()
            utc(now)
            require(plan.created_at <= report.created_at <= now < min(plan.expires_at, execution.expires_at),
                    ReasonCode.AUTHORIZATION_EXPIRED)
            values = dict(schema_version=ReportProof.SCHEMA, report_hash=report.report_hash,
                          execution_hash=content_hash(execution), context_hash=content_hash(context),
                          # Proofs were issued while active. Preserve those signed
                          # bytes, but load material with its current restricted status.
                          key=replace(self.key, status=KeyStatus.ACTIVE))
            if verifying:
                require(proof.content() == values, ReasonCode.REPORT_MISMATCH)
            # A separate HMAC scope prevents audit entries or other authenticated
            # metadata from being replayed as report proofs, even with the same key.
            mac_context = replace(context, field_ref='reports/mask-auth.v1')
            metadata = canonical_bytes({'domain': 'ds.mask-report-auth.v1', 'binding': values})
            if verifying:
                verified = self.crypto.verify_authentication(metadata, proof.authentication, mac_context, self.key)
                if isinstance(verified, ProtectionError):
                    return verified
                require(type(verified) is bool, ReasonCode.KEY_UNAVAILABLE)
                require(verified, ReasonCode.REPORT_MISMATCH)
                return True
            authentication = self.crypto.authenticate(metadata, mac_context, self.key)
            if isinstance(authentication, ProtectionError):
                return authentication
            require(type(authentication) is bytes and len(authentication) == 32, ReasonCode.KEY_UNAVAILABLE)
            return ReportProof(**values, authentication=authentication)
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id='reports/authenticate')
