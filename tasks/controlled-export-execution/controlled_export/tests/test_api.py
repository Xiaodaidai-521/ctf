import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

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
