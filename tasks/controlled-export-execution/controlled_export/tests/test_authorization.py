from datetime import timedelta

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from controlled_export.authorization import (
    receipt_obligation_ids,
    share_creation_constraints,
    sign_authorization,
    validate_authorization,
    validate_obligations,
)
from controlled_export.errors import AuthorizationRejected, ContractError

from .helpers import AUTHORITY_SECRET, authorization_for, csv_bytes, csv_plan


def _obligation(obligation_id, obligation_type, phase, parameters=None, version="1"):
    value = {
        "obligation_id": obligation_id,
        "type": obligation_type,
        "phase": phase,
        "parameters": parameters if parameters is not None else {},
    }
    if version is not None:
        value["version"] = version
    return value


@override_settings(
    CONTROLLED_EXPORT_ENVIRONMENT="evaluation",
    EXECUTION_AUTHORITY_HMAC_SECRET=AUTHORITY_SECRET,
)
class AuthorizationContractTests(SimpleTestCase):
    def test_signed_authorization_is_accepted(self):
        payload, signature = authorization_for(csv_bytes(), csv_plan())
        validated = validate_authorization(payload, signature)
        self.assertEqual(validated.payload["effective_action"], "mask")

    def test_not_executable_dispositions_are_rejected(self):
        for action in ("deny", "require_approval", "defer"):
            with self.subTest(action=action):
                payload, _ = authorization_for(csv_bytes(), csv_plan(), action=action)
                signature = sign_authorization(payload, AUTHORITY_SECRET)
                with self.assertRaisesRegex(AuthorizationRejected, "not executable"):
                    validate_authorization(payload, signature)

    def test_unknown_mandatory_obligation_is_rejected(self):
        payload, _ = authorization_for(csv_bytes(), csv_plan())
        payload["obligations"].append(
            {
                "obligation_id": "unknown-1",
                "type": "send_public_link",
                "phase": "before_publish",
                "parameters": {},
            }
        )
        signature = sign_authorization(payload, AUTHORITY_SECRET)
        with self.assertRaisesRegex(AuthorizationRejected, "Unsupported mandatory obligation"):
            validate_authorization(payload, signature)

    def test_expired_or_wrong_environment_authorization_is_rejected(self):
        payload, _ = authorization_for(
            csv_bytes(),
            csv_plan(),
            overrides={"valid_until": (timezone.now() - timedelta(seconds=1)).isoformat()},
        )
        with self.assertRaises(AuthorizationRejected):
            validate_authorization(payload, sign_authorization(payload, AUTHORITY_SECRET))
        payload, _ = authorization_for(csv_bytes(), csv_plan(), environment="production")
        with self.assertRaises(AuthorizationRejected):
            validate_authorization(payload, sign_authorization(payload, AUTHORITY_SECRET))


class ObligationContractTests(SimpleTestCase):
    def test_bind_recipient_is_required_and_normalized(self):
        obligations = validate_obligations(
            [_obligation("bind-1", "bind_recipient", "share_creation", {"recipient_id": "  42  "})]
        )
        self.assertEqual(obligations[0]["parameters"], {"recipient_id": "42"})
        self.assertEqual(share_creation_constraints(obligations), ("42", None))

    def test_bind_recipient_rejects_missing_blank_or_extra_parameters(self):
        for parameters in ({}, {"recipient_id": "   "}, {"recipient_id": "42", "mode": "email"}):
            with self.subTest(parameters=parameters), self.assertRaises(ContractError):
                validate_obligations(
                    [_obligation("bind-1", "bind_recipient", "share_creation", parameters)]
                )

    def test_set_expiry_requires_an_aware_timestamp_and_no_extra_parameters(self):
        naive = timezone.now().replace(tzinfo=None).isoformat()
        for parameters in (
            {},
            {"expires_at": naive},
            {"expires_at": "not-a-time"},
            {"expires_at": timezone.now().isoformat(), "grace_seconds": 60},
        ):
            with self.subTest(parameters=parameters), self.assertRaises(ContractError):
                validate_obligations(
                    [_obligation("expiry-1", "set_expiry", "share_creation", parameters)]
                )

    def test_record_receipt_requires_empty_parameters(self):
        validate_obligations([_obligation("receipt-1", "record_receipt", "post_delivery")])
        with self.assertRaises(ContractError):
            validate_obligations(
                [_obligation("receipt-1", "record_receipt", "post_delivery", {"channel": "email"})]
            )

    def test_obligation_version_must_be_the_string_one(self):
        for version in (2, 1, "2", ""):
            with self.subTest(version=version), self.assertRaises(ContractError):
                validate_obligations(
                    [_obligation("bind-1", "bind_recipient", "share_creation", {"recipient_id": "42"}, version)]
                )

    def test_obligation_version_defaults_to_one_when_omitted(self):
        obligations = validate_obligations(
            [_obligation("bind-1", "bind_recipient", "share_creation", {"recipient_id": "42"}, None)]
        )
        self.assertEqual(obligations[0]["version"], "1")

    def test_conflicting_bind_recipient_obligations_are_rejected(self):
        with self.assertRaises(ContractError):
            validate_obligations(
                [
                    _obligation("bind-1", "bind_recipient", "share_creation", {"recipient_id": "42"}),
                    _obligation("bind-2", "bind_recipient", "share_creation", {"recipient_id": "43"}),
                ]
            )

    def test_share_creation_constraints_use_the_earliest_expiry(self):
        later = (timezone.now() + timedelta(hours=2)).isoformat()
        earlier = (timezone.now() + timedelta(hours=1)).isoformat()
        obligations = validate_obligations(
            [
                _obligation("expiry-1", "set_expiry", "share_creation", {"expires_at": later}),
                _obligation("expiry-2", "set_expiry", "share_creation", {"expires_at": earlier}),
            ]
        )
        recipient_id, limit = share_creation_constraints(obligations)
        self.assertIsNone(recipient_id)
        self.assertEqual(limit, timezone.datetime.fromisoformat(earlier))

    def test_receipt_obligation_ids_are_reported(self):
        obligations = validate_obligations(
            [
                _obligation("receipt-1", "record_receipt", "post_delivery"),
                _obligation("receipt-2", "record_receipt", "post_delivery"),
                _obligation("redact-1", "redact", "before_publish"),
            ]
        )
        self.assertEqual(receipt_obligation_ids(obligations), ["receipt-1", "receipt-2"])

    def test_obligations_without_the_new_types_are_unchanged(self):
        obligations = validate_obligations(
            [
                _obligation("redact-1", "redact", "before_publish"),
                _obligation("formula-1", "sanitize_formulas", "before_publish"),
            ]
        )
        self.assertEqual([item["type"] for item in obligations], ["redact", "sanitize_formulas"])
        self.assertEqual(share_creation_constraints(obligations), (None, None))
        self.assertEqual(receipt_obligation_ids(obligations), [])
