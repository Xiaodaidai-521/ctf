from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from controlled_export.errors import AuthorizationRejected, IdempotencyConflict, UnsupportedContent
from controlled_export.models import ExecutionAttempt, ExportExecution, OutboxEvent, ProtectedArtifact
from controlled_export.services import _fail_execution, execute_authorized_export
from controlled_export.storage import PrivateStorage

from .helpers import IsolatedStorageMixin, authorization_for, csv_bytes, csv_plan


class ExecutionServiceTests(IsolatedStorageMixin, TestCase):
    def _execute(self, *, content=None, plan=None, authorization=None, signature=None, key="execute-1"):
        content = content or csv_bytes()
        plan = plan or csv_plan()
        if authorization is None:
            authorization, signature = authorization_for(content, plan)
        return execute_authorized_export(
            authorization=authorization,
            signature=signature,
            plan=plan,
            filename="synthetic.csv",
            content=content,
            idempotency_key=key,
            caller_id="risk-service",
        )

    def test_execution_creates_private_artifact_receipt_and_outbox(self):
        receipt, replay = self._execute()
        self.assertFalse(replay)
        self.assertEqual(receipt["status"], "succeeded")
        artifact = ProtectedArtifact.objects.get()
        self.assertNotIn(str(PrivateStorage().root), artifact.private_storage_ref)
        self.assertTrue(PrivateStorage().path(artifact.private_storage_ref).is_file())
        self.assertEqual(
            PrivateStorage().sha256(artifact.private_storage_ref),
            artifact.output_content_hash,
        )
        self.assertEqual(
            list(OutboxEvent.objects.values_list("event_type", flat=True)),
            ["execution.started", "execution.completed"],
        )

    def test_same_idempotency_key_and_content_returns_existing_result(self):
        authorization, signature = authorization_for(csv_bytes(), csv_plan())
        first, first_replay = self._execute(authorization=authorization, signature=signature)
        second, second_replay = self._execute(authorization=authorization, signature=signature)
        self.assertFalse(first_replay)
        self.assertTrue(second_replay)
        self.assertEqual(first["execution_id"], second["execution_id"])
        self.assertEqual(ExportExecution.objects.count(), 1)

    def test_same_idempotency_key_with_different_binding_conflicts(self):
        self._execute(key="shared-key")
        alternate, signature = authorization_for(csv_bytes(), csv_plan())
        with self.assertRaises(IdempotencyConflict):
            self._execute(authorization=alternate, signature=signature, key="shared-key")
        self.assertEqual(ExportExecution.objects.count(), 1)

    def test_switching_idempotency_key_cannot_reconsume_authorization(self):
        authorization, signature = authorization_for(csv_bytes(), csv_plan())
        self._execute(authorization=authorization, signature=signature, key="first-key")
        with self.assertRaisesRegex(AuthorizationRejected, "already been consumed"):
            self._execute(authorization=authorization, signature=signature, key="second-key")
        self.assertEqual(ExportExecution.objects.count(), 1)

    def test_transform_failure_never_registers_or_returns_original(self):
        content = csv_bytes()
        plan = csv_plan()
        plan["operations"][0]["type"] = "unknown_operation"
        authorization, signature = authorization_for(content, plan)
        with self.assertRaises(UnsupportedContent):
            self._execute(content=content, plan=plan, authorization=authorization, signature=signature)
        execution = ExportExecution.objects.get()
        self.assertEqual(execution.state, "failed")
        self.assertFalse(ProtectedArtifact.objects.exists())
        self.assertFalse(any(PrivateStorage().root.rglob("*.csv")))

    def test_stale_worker_cannot_overwrite_newer_execution_generation(self):
        now = timezone.now()
        execution = ExportExecution.objects.create(
            authorization_id="auth-stale",
            export_request_id="request-stale",
            decision_id="decision-stale",
            asset_version_id="asset-stale",
            input_content_hash="a" * 64,
            profile_id="profile-stale",
            request_fingerprint="b" * 64,
            scope_hash="c" * 64,
            effective_action="allow",
            obligations=[],
            valid_until=now + timedelta(minutes=5),
            environment="evaluation",
            data_domain="synthetic-domain",
            subject_id="synthetic-subject",
            state="running",
            fencing_token=2,
        )
        old_attempt = ExecutionAttempt.objects.create(
            execution=execution,
            attempt_no=1,
            fencing_token=1,
            lease_expires_at=now - timedelta(seconds=1),
        )
        new_attempt = ExecutionAttempt.objects.create(
            execution=execution,
            attempt_no=2,
            fencing_token=2,
            lease_expires_at=now + timedelta(minutes=5),
        )
        execution.active_attempt_id = new_attempt.attempt_id
        execution.save(update_fields=["active_attempt_id"])
        _fail_execution(execution.execution_id, old_attempt.attempt_id, 1, "OLD_WORKER")
        execution.refresh_from_db()
        new_attempt.refresh_from_db()
        self.assertEqual(execution.state, "running")
        self.assertEqual(execution.active_attempt_id, new_attempt.attempt_id)
        self.assertEqual(new_attempt.status, "running")
