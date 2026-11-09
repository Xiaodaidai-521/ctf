"""M8: call an injected M0 Detect, then map the three old reason codes."""
from data_security.contracts import (BASELINE_LIMITS, BoundedPayload, Category,
    ContractViolation, Detect, Finding, LocationKind, MediaType, PayloadKind, ProtectionError, ReasonCode)
from data_security.contracts.schema import require

_detect: Detect | None = None
_IMPLEMENTATIONS = {
    'email_ascii_v1': (Category.EMAIL, 'ASCII_EMAIL_SYNTAX'),
    'ipv4_v1': (Category.IPV4, 'IPV4_OCTETS_VALID'),
    'luhn_candidate_v1': (Category.CARD, 'LUHN_VALID_NOT_ACCOUNT_PROOF'),
}


def bind_detect(detector: Detect):
    global _detect
    require(callable(detector), ReasonCode.INVALID_TYPE)
    _detect = detector


def candidates(implementation, text):
    require(implementation in _IMPLEMENTATIONS, ReasonCode.UNSUPPORTED_FORMAT)
    require(_detect is not None, ReasonCode.POLICY_NOT_APPROVED)
    payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.TEXT,
        media_type=MediaType.TEXT, text=text, tree=None, binary=None, limits=BASELINE_LIMITS)
    try:
        result = _detect(payload, BASELINE_LIMITS)
        if type(result) is ProtectionError:
            raise ContractViolation(result.code)
        require(type(result) is tuple and len(result) <= BASELINE_LIMITS.max_findings and
                all(type(f) is Finding and f.location.kind is LocationKind.TEXT_SPAN and
                    f.location.end <= len(text) for f in result), ReasonCode.INVALID_COORDINATE)
        category, reason = _IMPLEMENTATIONS[implementation]
        return tuple(sorted((f.location.start, f.location.end, reason) for f in result if f.category is category))
    except ContractViolation:
        raise
    except Exception:
        raise ContractViolation(ReasonCode.SCOPE_INCOMPLETE) from None
