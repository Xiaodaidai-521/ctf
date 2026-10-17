from datetime import timedelta

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from controlled_export.authorization import sign_authorization, validate_authorization
from controlled_export.errors import AuthorizationRejected

from .helpers import AUTHORITY_SECRET, authorization_for, csv_bytes, csv_plan


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
