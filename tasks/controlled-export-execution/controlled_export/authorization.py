import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from django.conf import settings
from django.utils.dateparse import parse_datetime

from .errors import AuthorizationRejected, ContractError


SUPPORTED_OBLIGATIONS = {
    "redact": {"before_publish"},
    "sanitize_formulas": {"before_publish"},
    "bind_recipient": {"share_creation"},
    "set_expiry": {"share_creation"},
    "record_receipt": {"post_delivery"},
}
OBLIGATION_VERSION = "1"
STRICT_OBLIGATIONS = {"bind_recipient", "set_expiry", "record_receipt"}
REQUIRED_FIELDS = {
    "authorization_id",
    "execution_id",
    "export_request_id",
    "decision_id",
    "asset_version_id",
    "input_content_hash",
    "profile_id",
    "request_fingerprint",
    "scope_hash",
    "effective_action",
    "obligations",
    "valid_until",
    "environment",
    "data_domain",
    "subject_id",
}


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest_json(value):
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def sign_authorization(payload, secret):
    return hmac.new(secret.encode("utf-8"), canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def _bounded_string(payload, field, max_length=160, allow_blank=False):
    value = payload.get(field)
    if not isinstance(value, str) or len(value) > max_length or (not allow_blank and not value.strip()):
        raise ContractError(f"{field} must be a bounded non-empty string", code="AUTH_FIELD_INVALID")
    return value.strip()


def _valid_hash(payload, field, allow_blank=False):
    value = _bounded_string(payload, field, 64, allow_blank=allow_blank)
    if value or not allow_blank:
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
            raise ContractError(f"{field} must be a lowercase SHA-256 hex digest", code="AUTH_HASH_INVALID")
    return value.lower()


def _parse_aware_timestamp(raw, field):
    if not isinstance(raw, str):
        raise ContractError(f"{field} must be an ISO-8601 timestamp", code="AUTH_TIME_INVALID")
    value = parse_datetime(raw)
    if value is None or value.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone", code="AUTH_TIME_INVALID")
    return value


def _require_exact_parameters(parameters, expected):
    if set(parameters) != set(expected):
        raise ContractError(
            f"obligation parameters must contain exactly {sorted(expected)}",
            code="OBLIGATION_PARAMETERS_INVALID",
        )


def _normalized_obligation_parameters(obligation_type, parameters):
    if obligation_type == "bind_recipient":
        _require_exact_parameters(parameters, {"recipient_id"})
        recipient_id = parameters["recipient_id"]
        if not isinstance(recipient_id, str):
            raise ContractError("recipient_id must be a string", code="OBLIGATION_PARAMETERS_INVALID")
        recipient_id = recipient_id.strip()
        if not recipient_id or len(recipient_id) > 160:
            raise ContractError("recipient_id is invalid", code="OBLIGATION_PARAMETERS_INVALID")
        return {"recipient_id": recipient_id}
    if obligation_type == "set_expiry":
        _require_exact_parameters(parameters, {"expires_at"})
        _parse_aware_timestamp(parameters["expires_at"], "expires_at")
        return {"expires_at": parameters["expires_at"]}
    if obligation_type == "record_receipt":
        _require_exact_parameters(parameters, set())
        return {}
    return parameters


def validate_obligations(obligations):
    if not isinstance(obligations, list):
        raise ContractError("obligations must be a list", code="OBLIGATIONS_INVALID")
    seen = set()
    normalized = []
    bound_recipients = set()
    for obligation in obligations:
        if not isinstance(obligation, dict):
            raise ContractError("each obligation must be an object", code="OBLIGATION_INVALID")
        obligation_id = _bounded_string(obligation, "obligation_id")
        obligation_type = _bounded_string(obligation, "type", 80)
        phase = _bounded_string(obligation, "phase", 40)
        if obligation_id in seen:
            raise ContractError("obligation_id values must be unique", code="OBLIGATION_DUPLICATE")
        if obligation_type not in SUPPORTED_OBLIGATIONS or phase not in SUPPORTED_OBLIGATIONS[obligation_type]:
            raise AuthorizationRejected(
                f"Unsupported mandatory obligation {obligation_type!r} at phase {phase!r}",
                code="OBLIGATION_UNSUPPORTED",
            )
        parameters = obligation.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ContractError("obligation parameters must be an object", code="OBLIGATION_INVALID")
        version = obligation.get("version", OBLIGATION_VERSION)
        if obligation_type in STRICT_OBLIGATIONS:
            if not isinstance(version, str) or version != OBLIGATION_VERSION:
                raise ContractError(
                    f"{obligation_type} obligation requires version {OBLIGATION_VERSION!r}",
                    code="OBLIGATION_VERSION_UNSUPPORTED",
                )
            parameters = _normalized_obligation_parameters(obligation_type, parameters)
            if obligation_type == "bind_recipient":
                bound_recipients.add(parameters["recipient_id"])
        else:
            version = str(version)
        normalized.append(
            {
                "obligation_id": obligation_id,
                "type": obligation_type,
                "phase": phase,
                "parameters": parameters,
                "version": version,
            }
        )
        seen.add(obligation_id)
    if len(bound_recipients) > 1:
        raise ContractError(
            "conflicting bind_recipient obligations",
            code="OBLIGATION_CONFLICT",
        )
    return normalized


def share_creation_constraints(obligations):
    recipient_id = None
    expiry_limit = None
    for obligation in validate_obligations(obligations):
        if obligation["type"] == "bind_recipient":
            recipient_id = obligation["parameters"]["recipient_id"]
        elif obligation["type"] == "set_expiry":
            candidate = _parse_aware_timestamp(obligation["parameters"]["expires_at"], "expires_at")
            if expiry_limit is None or candidate < expiry_limit:
                expiry_limit = candidate
    return recipient_id, expiry_limit


def receipt_obligation_ids(obligations):
    return [
        obligation["obligation_id"]
        for obligation in validate_obligations(obligations)
        if obligation["type"] == "record_receipt"
    ]


@dataclass(frozen=True)
class ValidatedAuthorization:
    payload: dict
    valid_until: datetime
    obligations: list


def validate_authorization(payload, signature, *, now=None):
    if not isinstance(payload, dict):
        raise ContractError("authorization must be an object", code="AUTHORIZATION_INVALID")
    missing = sorted(REQUIRED_FIELDS.difference(payload))
    if missing:
        raise ContractError(f"authorization fields missing: {', '.join(missing)}", code="AUTH_FIELDS_MISSING")
    secret = settings.EXECUTION_AUTHORITY_HMAC_SECRET
    if not secret:
        raise AuthorizationRejected("Execution authority is not configured", code="AUTHORITY_UNAVAILABLE")
    expected = sign_authorization(payload, secret)
    if not isinstance(signature, str) or not hmac.compare_digest(expected, signature.lower()):
        raise AuthorizationRejected("Authorization signature is invalid", code="AUTH_SIGNATURE_INVALID")

    for field in (
        "authorization_id",
        "execution_id",
        "export_request_id",
        "decision_id",
        "asset_version_id",
        "profile_id",
        "environment",
        "data_domain",
        "subject_id",
    ):
        _bounded_string(payload, field)
    for field in ("input_content_hash", "request_fingerprint", "scope_hash"):
        _valid_hash(payload, field)
    _valid_hash(payload, "plan_hash", allow_blank=True)

    action = _bounded_string(payload, "effective_action", 24)
    if action not in {"allow", "mask"}:
        raise AuthorizationRejected(
            f"Disposition {action!r} is not executable",
            code="NOT_EXECUTABLE",
        )
    if payload["environment"] != settings.CONTROLLED_EXPORT_ENVIRONMENT:
        raise AuthorizationRejected("Authorization environment mismatch", code="ENVIRONMENT_MISMATCH")

    valid_until = _parse_aware_timestamp(payload["valid_until"], "valid_until")
    current = now or datetime.now(timezone.utc)
    if current >= valid_until:
        raise AuthorizationRejected("Authorization has expired", code="AUTHORIZATION_EXPIRED")
    obligations = validate_obligations(payload["obligations"])
    return ValidatedAuthorization(payload=payload, valid_until=valid_until, obligations=obligations)


def execution_request_fingerprint(payload, *, actual_input_hash, plan_hash, caller_id):
    binding = {
        "authorization_id": payload["authorization_id"],
        "asset_version_id": payload["asset_version_id"],
        "input_content_hash": actual_input_hash,
        "scope_hash": payload["scope_hash"],
        "plan_hash": plan_hash,
        "environment": payload["environment"],
        "data_domain": payload["data_domain"],
        "subject_id": payload["subject_id"],
        "caller_id": caller_id,
    }
    return digest_json(binding)
