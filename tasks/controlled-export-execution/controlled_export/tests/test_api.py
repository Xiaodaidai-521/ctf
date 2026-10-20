import io
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient

from controlled_export.models import ExportExecution, ProtectedArtifact

from .helpers import INTERNAL_KEY, IsolatedStorageMixin, authorization_for, csv_bytes, csv_plan


class InternalApiTests(IsolatedStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _payload(self):
        content = csv_bytes()
        plan = csv_plan()
        authorization, signature = authorization_for(content, plan)
        return content, plan, authorization, signature

    def test_execution_requires_trusted_service_authentication(self):
        content, plan, authorization, signature = self._payload()
        response = self.client.post(
            reverse("controlled-export-execute"),
            {
                "authorization": json.dumps(authorization),
                "plan": json.dumps(plan),
                "file": SimpleUploadedFile("synthetic.csv", content, content_type="text/csv"),
            },
            format="multipart",
            HTTP_X_AUTHORIZATION_SIGNATURE=signature,
            HTTP_IDEMPOTENCY_KEY="api-no-auth",
        )
        self.assertIn(response.status_code, {401, 403})

    def test_execution_response_exposes_receipt_but_not_private_path(self):
        content, plan, authorization, signature = self._payload()
        response = self.client.post(
            reverse("controlled-export-execute"),
            {
                "authorization": json.dumps(authorization),
                "plan": json.dumps(plan),
                "file": SimpleUploadedFile("synthetic.csv", content, content_type="text/csv"),
            },
            format="multipart",
            HTTP_X_INTERNAL_AUTHORIZATION=f"Bearer {INTERNAL_KEY}",
            HTTP_X_CALLER_ID="risk-service",
            HTTP_X_AUTHORIZATION_SIGNATURE=signature,
            HTTP_IDEMPOTENCY_KEY="api-execute-1",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "succeeded")
        self.assertNotIn("private_storage_ref", response.data)
        self.assertNotIn("token", response.data)


class ShareApiObligationTests(IsolatedStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self._production_override = override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production")
        self._production_override.enable()
        self.internal = APIClient()
        self.recipient = APIClient()
        self.user = get_user_model().objects.create_user(username="recipient-42", password="x")
        self.recipient.force_authenticate(user=self.user)

    def tearDown(self):
        self._production_override.disable()
        super().tearDown()

    def _obligations(self, *, recipient_id, expiry_limit):
        return [
            {
                "obligation_id": "bind-1",
                "type": "bind_recipient",
                "phase": "share_creation",
                "parameters": {"recipient_id": recipient_id},
                "version": "1",
            },
            {
                "obligation_id": "expiry-1",
                "type": "set_expiry",
                "phase": "share_creation",
                "parameters": {"expires_at": expiry_limit.isoformat()},
                "version": "1",
            },
            {
                "obligation_id": "receipt-1",
                "type": "record_receipt",
                "phase": "post_delivery",
                "parameters": {},
                "version": "1",
            },
        ]

    def _execute(self, content=None, plan=None, filename="synthetic.csv", key="api-execute", action="mask"):
        content = content if content is not None else csv_bytes()
        plan = plan if plan is not None else csv_plan()
        authorization, signature = authorization_for(
            content,
            plan,
            environment="production",
            action=action,
            overrides={"obligations": self._obligations(
                recipient_id=str(self.user.pk),
                expiry_limit=timezone.now() + timedelta(minutes=30),
            )},
        )
        response = self.internal.post(
            reverse("controlled-export-execute"),
            {
                "authorization": json.dumps(authorization),
                "plan": json.dumps(plan),
                "file": SimpleUploadedFile(filename, content, content_type="application/octet-stream"),
            },
            format="multipart",
            HTTP_X_INTERNAL_AUTHORIZATION=f"Bearer {INTERNAL_KEY}",
            HTTP_X_CALLER_ID="risk-service",
            HTTP_X_AUTHORIZATION_SIGNATURE=signature,
            HTTP_IDEMPOTENCY_KEY=key,
        )
        return response, authorization

    def _share(self, execution_id, *, recipient_id=None, expires_at=None, key="api-share"):
        return self.internal.post(
            reverse("controlled-export-share-create"),
            {
                "execution_id": execution_id,
                "recipient_id": recipient_id or str(self.user.pk),
                "allowed_operations": ["preview", "download"],
                "expires_at": (expires_at or timezone.now() + timedelta(minutes=5)).isoformat(),
            },
            format="json",
            HTTP_X_INTERNAL_AUTHORIZATION=f"Bearer {INTERNAL_KEY}",
            HTTP_X_CALLER_ID="delivery-service",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_full_execute_share_access_and_receipt_flow(self):
        executed, _ = self._execute()
        self.assertEqual(executed.status_code, 201, executed.data)

        shared = self._share(executed.data["execution_id"])
        self.assertEqual(shared.status_code, 201, shared.data)
        self.assertTrue(shared.data["token"])
        self.assertNotIn("private_storage_ref", json.dumps(shared.data))

        accessed = self.recipient.get(
            reverse(
                "controlled-export-share-access",
                kwargs={"share_id": shared.data["share_id"], "operation": "download"},
            ),
            HTTP_X_SHARE_TOKEN=shared.data["token"],
        )
        self.assertEqual(accessed.status_code, 200)
        delivered = b"".join(accessed.streaming_content)
        self.assertTrue(delivered)

        receipt = self.internal.post(
            reverse("controlled-export-delivery-result", kwargs={"delivery_id": accessed["X-Delivery-Id"]}),
            {
                "status": "completed",
                "bytes_sent": len(delivered),
                "evidence_ref": "sink-receipt-1",
            },
            format="json",
            HTTP_X_INTERNAL_AUTHORIZATION=f"Bearer {INTERNAL_KEY}",
            HTTP_X_CALLER_ID="delivery-service",
        )
        self.assertEqual(receipt.status_code, 200, receipt.data)
        self.assertEqual(receipt.data["status"], "completed")

    def test_share_creation_rejects_recipient_outside_signed_binding(self):
        executed, _ = self._execute()
        response = self._share(executed.data["execution_id"], recipient_id="999")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data["error_code"], "RECIPIENT_OBLIGATION_MISMATCH")
        self.assertNotIn("token", response.data)

    def test_share_creation_rejects_expiry_beyond_signed_limit(self):
        executed, _ = self._execute()
        response = self._share(
            executed.data["execution_id"],
            expires_at=timezone.now() + timedelta(hours=2),
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["error_code"], "SHARE_EXPIRY_OBLIGATION_EXCEEDED")
        self.assertNotIn("token", response.data)

    def test_execution_with_active_xlsx_header_fails_without_artifact(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Export"
        sheet.append(["=1+1", "note"])
        sheet.append(["value", "safe"])
        buffer = io.BytesIO()
        workbook.save(buffer)
        plan = {
            "version": "1",
            "format": "xlsx",
            "scope": {"worksheets": ["Export"], "columns": ["=1+1", "note"]},
            "operations": [{"type": "sanitize_formulas"}],
        }
        response, authorization = self._execute(
            content=buffer.getvalue(),
            plan=plan,
            filename="synthetic.xlsx",
            key="api-execute-xlsx",
            action="allow",
        )
        self.assertEqual(response.status_code, 422, response.data)
        execution = ExportExecution.objects.get(pk=authorization["execution_id"])
        self.assertEqual(execution.state, "failed")
        self.assertFalse(ProtectedArtifact.objects.filter(execution=execution).exists())
