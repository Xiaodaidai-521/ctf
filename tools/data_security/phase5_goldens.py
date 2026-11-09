"""Hash-only evidence for actual-byte, synthetic table conversion goldens."""
from dataclasses import replace
import hashlib
import json
import unittest

from data_security.adapters.tabular.codec import CODEC_VERSION, TableCodec
from data_security.contracts import BASELINE_LIMITS, MediaType, ProtectionError, ReasonCode
from data_security.tests.test_phase5_codec import binary
from data_security.tests.test_phase5_pipeline import OUTPUT_HASHES, PipelineGoldens, pipeline_fixture
from data_security.tests.test_source_plans import ASSET, convert
from tools.data_security.phase2_test_entry import SafeResult


def main():
    result = unittest.TextTestRunner(verbosity=2, buffer=True, resultclass=SafeResult).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(PipelineGoldens))
    if not result.wasSuccessful():
        return 1
    rows = []
    for family in ('mainline', 'legacy'):
        for fmt in ('csv', 'xlsx'):
            fixture, plan, output, content = pipeline_fixture(family, fmt)
            rows.append({'family': family, 'format': fmt, 'group': 'normal',
                'input_hash': hashlib.sha256(content).hexdigest(), 'source_version': plan.source.source_version,
                'source_hash': plan.source.source_plan_hash, 'source_scope_hash': plan.source.scope_hash,
                'parser_version': plan.source.parser_version, 'parser_config_hash': plan.source.parser_config_hash,
                'target_plan_hash': plan.plan_hash, 'adapter_version': plan.adapter_version,
                'codec_version': CODEC_VERSION, 'source_trust': plan.source.source_trust.value,
                'source_environment': plan.source.source_environment, 'target_approved': plan.approval is not None,
                'expected_output_hash': OUTPUT_HASHES[family + '-' + fmt],
                'actual_output_hash': hashlib.sha256(output).hexdigest(), 'difference_count': 0,
                'target_actions': len(plan.actions)})
            normal = rows[-1]
            limited = TableCodec(asset_version=ASSET).parse(
                binary(content, MediaType.CSV if fmt == 'csv' else MediaType.XLSX),
                replace(BASELINE_LIMITS, max_bytes=len(content) - 1))
            refused = convert(fixture, source_approval=None)
            for group, result, code in (('boundary', limited, ReasonCode.LIMIT_EXCEEDED),
                                        ('refusal', refused, ReasonCode.SOURCE_NOT_APPROVED)):
                assert isinstance(result, ProtectionError) and result.code is code
                rows.append({**normal, 'group': group, 'target_plan_hash': None,
                    'expected_output_hash': None, 'actual_output_hash': None,
                    'expected_reason': code.value, 'actual_reason': result.code.value,
                    'condition': 'input-byte-limit-minus-one' if group == 'boundary' else 'missing-source-approval',
                    'target_actions': 0})
    print(json.dumps({'version': 'ds.phase5.golden-evidence.v1', 'synthetic_only': True,
        'public_delivery': False, 'goldens': rows,
        'boundary_and_refusal_tests': ['data_security.tests.test_phase5_codec',
            'data_security.tests.test_source_plans', 'data_security.tests.test_phase5_parsed_artifacts']},
        ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
