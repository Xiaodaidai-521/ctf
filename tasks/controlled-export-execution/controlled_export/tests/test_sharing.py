from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from controlled_export.errors import AuthorizationRejected, ContractError, ExecutionConflict, ShareAccessDenied
from controlled_export.models import DeliveryAttempt, ExportExecution, OutboxEvent
from controlled_export.services import (
    authorize_share_access,
    create_share_grant,
    execute_authorized_export,
    record_delivery_result,
    revoke_share_grant,
    rotate_share_token,
    stream_delivery,
)
from controlled_export.storage import PrivateStorage

from .helpers import IsolatedStorageMixin, authorization_for, csv_bytes, csv_plan


class SharingServiceTests(IsolatedStorageMixin, TestCase):
    def _execution(self):
        content = csv_bytes()
        plan = csv_plan()
        authorization, signature = authorization_for(content, plan, environment="production")
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            receipt, _ = execute_authorized_export(
                authorization=authorization,
                signature=signature,
                plan=plan,
                filename="synthetic.csv",
                content=content,
                idempotency_key="execute-production",
                caller_id="risk-service",
            )
        return receipt["execution_id"]

    def _share(self, execution_id, key="share-1", expires_at=None):
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            return create_share_grant(
                execution_id=execution_id,
                recipient_id="42",
                allowed_operations=["preview", "download"],
                expires_at=expires_at or timezone.now() + timedelta(minutes=10),
                idempotency_key=key,
                caller_id="delivery-service",
            )

    def test_evaluation_execution_cannot_create_share(self):
        content = csv_bytes()
        plan = csv_plan()
        authorization, signature = authorization_for(content, plan)
        receipt, _ = execute_authorized_export(
            authorization=authorization,
            signature=signature,
            plan=plan,
            filename="synthetic.csv",
            content=content,
            idempotency_key="evaluation-execute",
            caller_id="risk-service",
        )
        with self.assertRaises(AuthorizationRejected):
            create_share_grant(
                execution_id=receipt["execution_id"],
                recipient_id="42",
                allowed_operations=["download"],
                expires_at=timezone.now() + timedelta(minutes=5),
                idempotency_key="evaluation-share",
                caller_id="delivery-service",
            )

    def test_token_is_returned_once_and_replay_requires_rotation(self):
        execution_id = self._execution()
        expires_at = timezone.now() + timedelta(minutes=10)
        share, token, replay = self._share(execution_id, expires_at=expires_at)
        self.assertFalse(replay)
        self.assertTrue(token)
        self.assertNotEqual(share.token_digest, token)
        replay_share, replay_token, replay = self._share(execution_id, expires_at=expires_at)
        self.assertTrue(replay)
        self.assertIsNone(replay_token)
        self.assertEqual(replay_share.share_id, share.share_id)
        serialized_events = str(list(OutboxEvent.objects.values_list("payload", flat=True)))
        self.assertNotIn(token, serialized_events)

    def test_recipient_token_expiry_and_revocation_are_checked_at_admission(self):
        execution_id = self._execution()
        share, token, _ = self._share(execution_id)
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            with self.assertRaises(ShareAccessDenied):
                authorize_share_access(
                    share_id=share.share_id, recipient_id="not-42", token=token, operation="download"
                )
            with self.assertRaises(ShareAccessDenied):
                authorize_share_access(
                    share_id=share.share_id, recipient_id="42", token="wrong", operation="download"
                )
            delivery, artifact = authorize_share_access(
                share_id=share.share_id, recipient_id="42", token=token, operation="download"
            )
            self.assertEqual(delivery.status, "not_started")
            self.assertEqual(artifact.output_asset_version_id, share.artifact_id)
            share.expires_at = share.created_at + timedelta(microseconds=1)
            share.save(update_fields=["expires_at"])
            with self.assertRaises(ShareAccessDenied):
                authorize_share_access(
                    share_id=share.share_id, recipient_id="42", token=token, operation="download"
                )
            share.expires_at = timezone.now() + timedelta(minutes=5)
            share.save(update_fields=["expires_at"])
            revoke_share_grant(share_id=share.share_id, caller_id="delivery-service")
            with self.assertRaises(ShareAccessDenied):
                authorize_share_access(
                    share_id=share.share_id, recipient_id="42", token=token, operation="download"
                )
        self.assertGreaterEqual(OutboxEvent.objects.filter(event_type="share.access_denied").count(), 4)

    def test_repeated_downloads_receive_distinct_delivery_ids(self):
        execution_id = self._execution()
        share, token, _ = self._share(execution_id)
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            first, _ = authorize_share_access(
                share_id=share.share_id, recipient_id="42", token=token, operation="download"
            )
            second, _ = authorize_share_access(
                share_id=share.share_id, recipient_id="42", token=token, operation="download"
            )
        self.assertNotEqual(first.delivery_id, second.delivery_id)

    def test_rotation_invalidates_old_token(self):
        execution_id = self._execution()
        share, old_token, _ = self._share(execution_id)
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            _, new_token = rotate_share_token(share_id=share.share_id, caller_id="delivery-service")
            with self.assertRaises(ShareAccessDenied):
                authorize_share_access(
                    share_id=share.share_id, recipient_id="42", token=old_token, operation="preview"
                )
            delivery, _ = authorize_share_access(
                share_id=share.share_id, recipient_id="42", token=new_token, operation="preview"
            )
        self.assertIsNotNone(delivery.delivery_id)

    def test_stream_exhaustion_is_unknown_until_external_receipt(self):
        execution_id = self._execution()
        share, token, _ = self._share(execution_id)
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            delivery, artifact = authorize_share_access(
                share_id=share.share_id, recipient_id="42", token=token, operation="download"
            )
            transmitted = b"".join(stream_delivery(delivery, artifact, chunk_size=4))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "unknown")
        self.assertEqual(delivery.bytes_sent, len(transmitted))
        confirmed, replay = record_delivery_result(
            delivery_id=delivery.delivery_id,
            status="completed",
            bytes_sent=len(transmitted),
            evidence_ref="sink-receipt-1",
        )
        self.assertFalse(replay)
        self.assertEqual(confirmed.status, "completed")
        with self.assertRaises(ExecutionConflict):
            record_delivery_result(
                delivery_id=delivery.delivery_id,
                status="completed",
                bytes_sent=len(transmitted) + 1,
                evidence_ref="sink-receipt-2",
            )

    def test_completed_delivery_requires_evidence(self):
        delivery = DeliveryAttempt(status="started")
        with self.assertRaises(ContractError):
            record_delivery_result(
                delivery_id=delivery.delivery_id,
                status="completed",
                bytes_sent=1,
                evidence_ref="",
            )

    def test_tampered_artifact_is_denied_and_marked_for_repair(self):
        execution_id = self._execution()
        share, token, _ = self._share(execution_id)
        artifact_path = PrivateStorage().path(share.artifact.private_storage_ref)
        artifact_path.write_bytes(b"tampered")
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            with self.assertRaises(ShareAccessDenied):
                authorize_share_access(
                    share_id=share.share_id, recipient_id="42", token=token, operation="download"
                )
        execution = ExportExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.state, "repair_required")
