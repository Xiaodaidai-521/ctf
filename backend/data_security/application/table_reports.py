"""Build private report candidates from owner-loaded plans, never client reports.

No reserve, publish, settlement or delivery occurs here. ExportFlow must persist
and recheck the returned candidate, proof and current owner authorization.
"""
from dataclasses import dataclass, replace
import hashlib

from data_security.contracts import (
    CanaryCheckPort, ContractViolation, Coverage, MaskReport, Outcome, Outlet,
    ProtectionContext, ProtectionError, ReasonCode,
    ReportProof, ScanState, StoredObject, Unit, Unresolved, canonical_bytes, content_hash,
)
from data_security.contracts.schema import require
from data_security.core.redaction import apply_actions, detect, detect_table


@dataclass(frozen=True, slots=True, repr=False)
class ReportCandidate:
    stored: StoredObject
    report: MaskReport
    proof: ReportProof


class TableReportExecutor:
    def __init__(self, *, codec_factory, crypto, data_key, store, authenticator, limits, clock,
                 canary: CanaryCheckPort | None = None, canary_context_factory=None, stage_candidate=None):
        self.codec_factory, self.crypto, self.data_key = codec_factory, crypto, data_key
        self.store, self.authenticator, self.limits, self.clock = store, authenticator, limits, clock
        self.canary, self.canary_context_factory = canary, canary_context_factory
        self.stage_candidate = stage_candidate

    def prepare(self, payload, plan, execution, context, *, canary_context=None):
        """All inputs come from the trusted owner path; no report/hash parameter exists."""
        try:
            if self.canary is not None:
                if self.canary_context_factory is not None:
                    canary_context = self.canary_context_factory(plan, execution, context)
                    if type(canary_context) is ProtectionError:
                        return canary_context
                # The owner supplies the check authority; an ObjectContext cannot mint it.
                require(type(canary_context) is ProtectionContext and
                        canary_context.outlet is Outlet.EXPORT and
                        canary_context.environment is context.environment and
                        canary_context.environment.value == execution.environment and
                        canary_context.domain == execution.domain_ref and
                        canary_context.actor_ref == execution.subject_ref and
                        canary_context.authorization_ref == context.authorization_ref == execution.authorization_id and
                        (canary_context.object_ref, canary_context.object_version) ==
                        (context.object_uuid, context.object_version) and
                        canary_context.trace_id == execution.execution_id,
                        ReasonCode.AUTHORIZATION_DENIED)
            require(not plan.unresolved, ReasonCode.SCOPE_INCOMPLETE)
            require(plan.created_at <= self.clock() < min(plan.expires_at, execution.expires_at),
                    ReasonCode.AUTHORIZATION_EXPIRED)
            require(plan.limits == self.limits, ReasonCode.LIMIT_EXCEEDED)
            codec = self.codec_factory(asset_version=plan.asset_version)
            source = codec.parse(payload, self.limits)
            if isinstance(source, ProtectionError):
                return source
            plan.validate_snapshot(source)
            input_hash = hashlib.sha256(payload.binary).hexdigest()
            require(input_hash == source.input_hash == plan.input_hash, ReasonCode.HASH_MISMATCH)

            # Explicit scope projection retains original coordinates. The frozen
            # serializer still refuses missing headers, gaps and non-rectangles.
            scopes = {s.sheet_id: s for s in plan.scope.sheets}
            for scope in plan.scope.sheets:
                require(scope.includes_header and scope.row_ranges[0][0] == 1,
                        ReasonCode.UNSUPPORTED_SCOPE)
            columns = {(c.sheet_id, c.column_id): c for c in source.columns}
            selected = tuple(c for c in source.cells if c.sheet_id in scopes and
                c.column_id in scopes[c.sheet_id].column_ids and
                any(start <= c.source_row <= end for start, end in scopes[c.sheet_id].row_ranges))
            expected = sum(len(s.column_ids) * sum(end - start + 1 for start, end in s.row_ranges)
                           for s in plan.scope.sheets)
            require(len(selected) == expected, ReasonCode.SCOPE_INCOMPLETE)
            coverage = replace(source.coverage, total=len(selected), eligible=len(selected),
                               processed=len(selected), excluded=0)
            scoped = replace(source, sheet_ids=tuple(scopes), cells=selected, coverage=coverage,
                columns=tuple(columns[s.sheet_id, c] for s in plan.scope.sheets for c in s.column_ids))
            findings = detect_table(scoped, self.limits)
            protected = apply_actions(scoped, plan.actions, self.limits,
                environment=context.environment, domain=execution.domain_ref, scope=context.field_ref)
            output = codec.serialize(protected, self.limits)
            if isinstance(output, ProtectionError):
                return output

            # Scan the actual serialized bytes, not the pre-serialization grid.
            delivered = codec.parse(output, self.limits)
            if isinstance(delivered, ProtectionError):
                return delivered
            metadata = codec.delivery_metadata(delivered, self.limits)
            if isinstance(metadata, ProtectionError):
                return metadata
            if self.canary is not None:
                for checked in (delivered, metadata):
                    alerts = self.canary.check(payload=checked, context=canary_context)
                    if type(alerts) is ProtectionError:
                        return alerts
                    require(type(alerts) is tuple, ReasonCode.AUDIT_UNAVAILABLE)
                    require(not alerts, ReasonCode.SCOPE_INCOMPLETE)
            require(not detect_table(delivered, self.limits), ReasonCode.SCOPE_INCOMPLETE)
            metadata_hits = detect(metadata, self.limits)
            if isinstance(metadata_hits, ProtectionError):
                return metadata_hits
            require(not metadata_hits, ReasonCode.SCOPE_INCOMPLETE)
            # Canonical roundtrip also rejects unrepresented OOXML channels.
            # A parse which drops docProps/comments cannot certify those bytes.
            canonical = codec.serialize(delivered, self.limits)
            if isinstance(canonical, ProtectionError):
                return canonical
            require(canonical.binary == output.binary, ReasonCode.SCOPE_INCOMPLETE)
            output_hash = hashlib.sha256(output.binary).hexdigest()
            envelope = self.crypto.seal(output, context, self.data_key)
            if isinstance(envelope, ProtectionError):
                return envelope
            ciphertext_hash = hashlib.sha256(canonical_bytes(envelope)).hexdigest()
            if self.stage_candidate is not None:
                self.stage_candidate(plan, execution, context, envelope)
            candidate = self.store.write_candidate(envelope, context)
            if isinstance(candidate, ProtectionError):
                return candidate
            verified = self.store.verify(candidate, context)
            if isinstance(verified, ProtectionError):
                return verified
            require(verified.state == 'verified' and verified.ciphertext_hash == ciphertext_hash and
                    verified.version == context.object_version, ReasonCode.REPORT_MISMATCH)

            excluded_count = len(source.cells) - len(selected)
            excluded = (Unresolved(schema_version=Unresolved.SCHEMA, location=None,
                reason=ReasonCode.AUTHORIZATION_DENIED,
                source_ref='scope/outside/' + content_hash(plan.scope)),) if excluded_count else ()
            # Source processing uses cells (including dropped cells). Output
            # inspection uses fields: emitted cells plus retained sheet titles.
            inspected = len(delivered.cells) + len(metadata.tree.to_value())
            values = dict(schema_version=MaskReport.SCHEMA, execution_id=execution.execution_id,
                executor_ref=self.authenticator.executor_ref, asset_version=plan.asset_version,
                source=plan.source, action_plan_hash=plan.plan_hash, input_hash=input_hash,
                output_hash=output_hash, ciphertext_hash=ciphertext_hash, policy_binding=plan.policy_binding,
                algorithm_versions=tuple(sorted({a.algorithm.algorithm.value + '/' + a.algorithm.version
                                                  for a in plan.actions})),
                coverage=replace(coverage, total=len(source.cells), excluded=excluded_count),
                hit_count=len(findings), excluded=excluded, unresolved=(), rescan_state=ScanState.COMPLETE,
                rescan_coverage=Coverage(schema_version=Coverage.SCHEMA, unit=Unit.FIELD,
                    total=inspected, eligible=inspected, processed=inspected, excluded=0, failed=0,
                    unknown=0, unscanned=0, version='table-delivery-fields.v1'),
                outcome=Outcome.SUCCEEDED, created_at=self.clock())
            report = MaskReport(**values, report_hash=content_hash(values))
            proof = self.authenticator.issue(report, execution, plan, context, input_hash=input_hash,
                                             output_hash=output_hash, ciphertext_hash=ciphertext_hash)
            if isinstance(proof, ProtectionError):
                return proof
            return ReportCandidate(verified, report, proof)
        except ContractViolation as error:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=error.code,
                                   retryable=False, trace_id='reports/prepare')
