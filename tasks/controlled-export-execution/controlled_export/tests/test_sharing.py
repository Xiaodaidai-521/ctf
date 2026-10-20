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
    def _execution(self, obligations=None):
        content = csv_bytes()
        plan = csv_plan()
        overrides = {"obligations": obligations} if obligations is not None else None
        authorization, signature = authorization_for(
            content, plan, environment="production", overrides=overrides
        )
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

    def _share(self, execution_id, key="share-1", expires_at=None, recipient_id="42"):
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            return create_share_grant(
                execution_id=execution_id,
                recipient_id=recipient_id,
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


class ShareObligationEnforcementTests(IsolatedStorageMixin, TestCase):
    def _obligations(self, *, recipient="42", expiry_limit=None):
        obligations = [
            {
                "obligation_id": "bind-1",
                "type": "bind_recipient",
                "phase": "share_creation",
                "parameters": {"recipient_id": recipient},
                "version": "1",
            }
        ]
        if expiry_limit is not None:
            obligations.append(
                {
                    "obligation_id": "expiry-1",
                    "type": "set_expiry",
                    "phase": "share_creation",
                    "parameters": {"expires_at": expiry_limit.isoformat()},
                    "version": "1",
                }
            )
        return obligations

    def _execution(self, obligations):
        content = csv_bytes()
        plan = csv_plan()
        authorization, signature = authorization_for(
            content, plan, environment="production", overrides={"obligations": obligations}
        )
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            receipt, _ = execute_authorized_export(
                authorization=authorization,
                signature=signature,
                plan=plan,
                filename="synthetic.csv",
                content=content,
                idempotency_key="execute-obligations",
                caller_id="risk-service",
            )
        return receipt["execution_id"]

    def _share(self, execution_id, *, recipient_id="42", expires_at=None, key="share-1"):
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            return create_share_grant(
                execution_id=execution_id,
                recipient_id=recipient_id,
                allowed_operations=["download"],
                expires_at=expires_at or timezone.now() + timedelta(minutes=5),
                idempotency_key=key,
                caller_id="delivery-service",
            )

    def test_share_creation_rejects_recipient_outside_signed_binding(self):
        execution_id = self._execution(self._obligations(recipient="42"))
        with self.assertRaises(AuthorizationRejected):
            self._share(execution_id, recipient_id="43")

    def test_share_creation_normalizes_recipient_whitespace(self):
        execution_id = self._execution(self._obligations(recipient="42"))
        share, token, replay = self._share(execution_id, recipient_id="  42  ")
        self.assertFalse(replay)
        self.assertEqual(share.recipient_id, "42")
        self.assertTrue(token)

    def test_share_creation_rejects_expiry_beyond_signed_limit(self):
        limit = timezone.now() + timedelta(minutes=5)
        execution_id = self._execution(self._obligations(expiry_limit=limit))
        with self.assertRaises(ContractError):
            self._share(execution_id, expires_at=timezone.now() + timedelta(minutes=10))

    def test_share_creation_accepts_earlier_expiry(self):
        limit = timezone.now() + timedelta(minutes=10)
        execution_id = self._execution(self._obligations(expiry_limit=limit))
        share, _, replay = self._share(execution_id, expires_at=timezone.now() + timedelta(minutes=2))
        self.assertFalse(replay)
        self.assertLess(share.expires_at, limit)

    def test_idempotent_replay_rejects_share_that_violates_obligations(self):
        execution_id = self._execution(self._obligations(recipient="42"))
        expires_at = timezone.now() + timedelta(minutes=5)
        share, _, _ = self._share(execution_id, expires_at=expires_at)
        share.recipient_id = "43"
        share.save(update_fields=["recipient_id"])
        with self.assertRaises(AuthorizationRejected):
            self._share(execution_id, expires_at=expires_at)

    def test_share_access_denies_share_that_violates_obligations(self):
        execution_id = self._execution(self._obligations(recipient="42"))
        share, token, _ = self._share(execution_id)
        share.recipient_id = "43"
        share.save(update_fields=["recipient_id"])
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            with self.assertRaises(ShareAccessDenied):
                authorize_share_access(
                    share_id=share.share_id, recipient_id="43", token=token, operation="download"
                )
        self.assertEqual(DeliveryAttempt.objects.filter(share=share).count(), 0)

    def test_token_rotation_denies_share_that_violates_obligations(self):
        execution_id = self._execution(self._obligations(recipient="42"))
        share, _, _ = self._share(execution_id)
        share.recipient_id = "43"
        share.save(update_fields=["recipient_id"])
        with self.assertRaises(ShareAccessDenied):
            rotate_share_token(share_id=share.share_id, caller_id="delivery-service")

    def test_receipt_events_link_obligation_and_keep_full_evidence(self):
        execution_id = self._execution(
            [
                {
                    "obligation_id": "receipt-1",
                    "type": "record_receipt",
                    "phase": "post_delivery",
                    "parameters": {},
                    "version": "1",
                }
            ]
        )
        share, token, _ = self._share(execution_id)
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            delivery, artifact = authorize_share_access(
                share_id=share.share_id, recipient_id="42", token=token, operation="download"
            )
            transmitted = b"".join(stream_delivery(delivery, artifact, chunk_size=4))
        unknown_event = OutboxEvent.objects.filter(event_type="delivery.unknown").latest("created_at")
        self.assertEqual(unknown_event.payload["obligation_ids"], ["receipt-1"])
        self.assertIsNone(unknown_event.payload.get("evidence_ref"))
        self.assertEqual(unknown_event.payload["execution_id"], execution_id)
        self.assertFalse(unknown_event.payload["receipt_confirmed"])

        long_evidence = "sink-receipt-" + "x" * 200
        record_delivery_result(
            delivery_id=delivery.delivery_id,
            status="completed",
            bytes_sent=len(transmitted),
            evidence_ref=long_evidence,
        )
        completed_event = OutboxEvent.objects.filter(event_type="delivery.completed").latest("created_at")
        self.assertEqual(completed_event.payload["obligation_ids"], ["receipt-1"])
        self.assertEqual(completed_event.payload["evidence_ref"], long_evidence)
        self.assertEqual(completed_event.payload["execution_id"], execution_id)
        self.assertTrue(completed_event.payload["receipt_confirmed"])

    def test_unconsumed_delivery_claims_no_receipt(self):
        execution_id = self._execution(
            [
                {
                    "obligation_id": "receipt-1",
                    "type": "record_receipt",
                    "phase": "post_delivery",
                    "parameters": {},
                    "version": "1",
                }
            ]
        )
        share, token, _ = self._share(execution_id)
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            delivery, _ = authorize_share_access(
                share_id=share.share_id, recipient_id="42", token=token, operation="download"
            )
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "not_started")
        self.assertFalse(
            OutboxEvent.objects.filter(
                aggregate_type="delivery",
                aggregate_id=str(delivery.delivery_id),
                event_type__in=["delivery.started", "delivery.unknown", "delivery.completed", "delivery.failed"],
            ).exists()
        )
        accessed = OutboxEvent.objects.get(
            aggregate_type="delivery",
            aggregate_id=str(delivery.delivery_id),
            event_type="share.accessed",
        )
        self.assertNotIn("obligation_ids", accessed.payload)

    def test_invalid_persisted_obligations_fail_closed_everywhere(self):
        execution_id = self._execution(self._obligations(recipient="42"))
        share, token, _ = self._share(execution_id)
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            delivery, artifact = authorize_share_access(
                share_id=share.share_id, recipient_id="42", token=token, operation="download"
            )
        ExportExecution.objects.filter(pk=execution_id).update(
            obligations=[
                {
                    "obligation_id": "bind-1",
                    "type": "bind_recipient",
                    "phase": "share_creation",
                    "parameters": {},
                    "version": "1",
                }
            ]
        )
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"):
            with self.assertRaises(ShareAccessDenied):
                authorize_share_access(
                    share_id=share.share_id, recipient_id="42", token=token, operation="download"
                )
        self.assertEqual(DeliveryAttempt.objects.filter(share=share).count(), 1)
        with self.assertRaises(ShareAccessDenied):
            rotate_share_token(share_id=share.share_id, caller_id="delivery-service")
        with self.assertRaises(ContractError):
            self._share(execution_id)
        with self.assertRaises(ContractError):
            record_delivery_result(
                delivery_id=delivery.delivery_id,
                status="completed",
                bytes_sent=1,
                evidence_ref="sink-receipt-1",
            )
        with self.assertRaises(ContractError):
            b"".join(stream_delivery(delivery, artifact, chunk_size=4))
