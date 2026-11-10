"""Read-only report statistics; neither stored rows nor MACs prove delivery."""
from django.db import DatabaseError

from data_security.contracts import ContractViolation, FrozenJSON, ProtectionError, ReasonCode
from data_security.adapters.persistence.models import ExportReport


def read_statistics(offset, *, reports, verify_report, capabilities, clock, limits):
    try:
        selected = list(ExportReport.objects.order_by('-pk').values_list('pk', 'execution_id')[offset:offset + 21])
        items = []
        for record_id, execution_id in selected[:20]:
            item = {'id': record_id, 'integrity': 'unknown', 'reason': None, 'measurements': [], 'versions': None}
            binding = reports.load_binding(execution_id)
            record = binding if isinstance(binding, ProtectionError) else reports.read(binding)
            if isinstance(record, ProtectionError):
                item['reason'] = record.code.value
            elif record is None:
                item['reason'] = 'REPORT_NOT_AVAILABLE'
            else:
                verified = verify_report(record)
                if verified is not True:
                    item['reason'] = verified.code.value if isinstance(verified, ProtectionError) else 'REPORT_MISMATCH'
                else:
                    report = record.report
                    item.update(integrity='verified', created_at=report.created_at.isoformat(),
                        environment=record.binding.environment, source_trust=report.source.source_trust.value,
                        rescan_state=report.rescan_state.value,
                        versions={'report': report.schema_version, 'policy_binding': report.policy_binding.to_wire(),
                            'algorithms': list(report.algorithm_versions), 'adapter': record.plan.adapter_version,
                            'coordinate': record.plan.scope.coordinate_version,
                            'source_format': report.source.source_format.value,
                            'source': report.source.source_version, 'source_record': report.source.source_record_version,
                            'parser': report.source.parser_version, 'operation': report.source.operation_contract_version,
                            'asset': report.asset_version, 'audit_key': record.proof.key.to_wire()})
                    for stage, coverage in (('processing', report.coverage), ('rescan', report.rescan_coverage)):
                        item['measurements'].append(dict(coverage.to_wire(), stage=stage,
                            numerator=coverage.processed, denominator=coverage.eligible, ratio=coverage.ratio,
                            zero_reason='NO_ELIGIBLE_UNITS' if coverage.eligible == 0 else None))
            items.append(item)
        # Missing denominators are not measured 0/0, and unknown rows are not units.
        unknown_sources = [dict(source=source, unit=unit, numerator=None, denominator=None,
            ratio=None, zero_reason=None, reason=reason, version=None) for source, unit, reason in (
                ('field-protection', 'field', 'COVERAGE_NOT_RECORDED'),
                ('text-rag', 'text', 'COVERAGE_NOT_RECORDED'),
                ('enabled-outlets', 'outlet', 'BASELINE_UNVERIFIED'))]
        return FrozenJSON({'state': 'enabled-unverified', 'scope': 'retained-report-page',
            'observed_at': clock().isoformat(), 'capabilities': capabilities,
            'items': items, 'offset': offset, 'limit': 20,
            'next_offset': offset + 20 if len(selected) > 20 else None,
            'unknown_records': sum(item['integrity'] == 'unknown' for item in items),
            'unknown_sources': unknown_sources}, max_depth=limits.max_json_depth,
            max_nodes=limits.max_json_nodes, max_fields=limits.max_json_fields,
            max_text_chars=limits.max_text_chars, max_bytes=limits.max_json_bytes)
    except ContractViolation as error:
        code = error.code
    except DatabaseError:
        code = ReasonCode.AUDIT_UNAVAILABLE
    return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                           retryable=False, trace_id='statistics/read')
