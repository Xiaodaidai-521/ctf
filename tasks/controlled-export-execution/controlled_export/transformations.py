"""Thin retained execution facade over the installable M8/M1 library."""
from dataclasses import dataclass

from data_security.contracts import BASELINE_LIMITS, ContractViolation
from data_security.application.legacy_tabular import fixed_replace
from data_security.adapters.tabular.codec import FORMULA_PREFIXES, neutralize_formula
from data_security.adapters.tabular.column_v1 import PlanError, transform_columns

from .authorization import digest_json, sha256_bytes
from .errors import ContractError, UnsupportedContent


@dataclass(frozen=True)
class TransformResult:
    content: bytes
    output_format: str
    suffix: str
    processed_records: int
    output_records: int
    output_hash: str
    scope_hash: str
    plan_hash: str


def _transform(content, plan, effective_action, input_format, limits):
    try:
        result, count = transform_columns(content, input_format, plan, effective_action, limits, fixed_replace)
    except PlanError as exc:
        error = UnsupportedContent if exc.unsupported else ContractError
        raise error('Table transformation rejected', code=exc.code) from None
    except ContractViolation as exc:
        raise UnsupportedContent('Table contract rejected', code=exc.code.value) from None
    return TransformResult(content=result, output_format=input_format, suffix='.' + input_format,
        processed_records=count, output_records=count, output_hash=sha256_bytes(result),
        scope_hash=digest_json(plan['scope']), plan_hash=digest_json(plan))


def transform_csv(content, plan, effective_action, *, limits=BASELINE_LIMITS):
    return _transform(content, plan, effective_action, 'csv', limits)


def transform_xlsx(content, plan, effective_action, *, limits=BASELINE_LIMITS):
    return _transform(content, plan, effective_action, 'xlsx', limits)


def transform(content, filename, plan, effective_action, *, limits=BASELINE_LIMITS):
    if not isinstance(content, bytes) or not content:
        raise UnsupportedContent('Input content is empty', code='INPUT_EMPTY')
    if len(content) > limits.max_bytes:
        raise UnsupportedContent('Input size limit exceeded', code='INPUT_SIZE_LIMIT')
    lowered = filename.lower()
    if lowered.endswith('.csv'):
        return transform_csv(content, plan, effective_action, limits=limits)
    if lowered.endswith('.xlsx'):
        return transform_xlsx(content, plan, effective_action, limits=limits)
    raise UnsupportedContent('Only CSV and XLSX are supported', code='FORMAT_UNSUPPORTED')
