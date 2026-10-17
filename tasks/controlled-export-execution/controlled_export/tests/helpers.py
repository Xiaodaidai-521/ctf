import csv
import io
import tempfile
import uuid
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from controlled_export.authorization import digest_json, execution_request_fingerprint, sha256_bytes, sign_authorization


AUTHORITY_SECRET = "test-authority-secret"
TOKEN_PEPPER = "test-token-pepper"
INTERNAL_KEY = "test-internal-key"


def csv_bytes(rows=None):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows or [["name", "email", "note"], ["Alice", "alice@example.invalid", "=1+1"]])
    return output.getvalue().encode("utf-8")


def csv_plan():
    return {
        "version": "1",
        "format": "csv",
        "scope": {"columns": ["name", "email", "note"]},
        "operations": [
            {"type": "mask_columns", "columns": ["email"], "strategy": "fixed", "value": "***"},
            {"type": "sanitize_formulas"},
        ],
    }


def authorization_for(content, plan, *, caller_id="risk-service", environment="evaluation", action="mask", overrides=None):
    execution_id = str(uuid.uuid4())
    payload = {
        "authorization_id": f"auth-{uuid.uuid4()}",
        "execution_id": execution_id,
        "export_request_id": f"request-{uuid.uuid4()}",
        "decision_id": f"decision-{uuid.uuid4()}",
        "asset_version_id": f"asset-{uuid.uuid4()}",
        "input_content_hash": sha256_bytes(content),
        "profile_id": f"profile-{uuid.uuid4()}",
        "request_fingerprint": "0" * 64,
        "scope_hash": digest_json(plan["scope"]),
        "effective_action": action,
        "obligations": [
            {
                "obligation_id": "redact-1",
                "type": "redact",
                "phase": "before_publish",
                "parameters": {},
                "version": "1",
            },
            {
                "obligation_id": "receipt-1",
                "type": "record_receipt",
                "phase": "post_delivery",
                "parameters": {},
                "version": "1",
            },
        ],
        "plan_id": f"plan-{uuid.uuid4()}",
        "plan_hash": digest_json(plan),
        "reservation_id": f"reservation-{uuid.uuid4()}",
        "valid_until": (timezone.now() + timedelta(minutes=15)).isoformat(),
        "environment": environment,
        "data_domain": "synthetic-domain",
        "subject_id": "synthetic-subject",
    }
    if overrides:
        payload.update(overrides)
    payload["request_fingerprint"] = execution_request_fingerprint(
        payload,
        actual_input_hash=payload["input_content_hash"],
        plan_hash=payload["plan_hash"],
        caller_id=caller_id,
    )
    return payload, sign_authorization(payload, AUTHORITY_SECRET)


class IsolatedStorageMixin:
    def setUp(self):
        super().setUp()
        self._storage_temp = tempfile.TemporaryDirectory()
        self._settings_override = override_settings(
            CONTROLLED_EXPORT_PRIVATE_ROOT=self._storage_temp.name,
            CONTROLLED_EXPORT_ENVIRONMENT="evaluation",
            CONTROLLED_EXPORT_INTERNAL_KEY=INTERNAL_KEY,
            EXECUTION_AUTHORITY_HMAC_SECRET=AUTHORITY_SECRET,
            SHARE_TOKEN_PEPPER=TOKEN_PEPPER,
        )
        self._settings_override.enable()

    def tearDown(self):
        self._settings_override.disable()
        self._storage_temp.cleanup()
        super().tearDown()
