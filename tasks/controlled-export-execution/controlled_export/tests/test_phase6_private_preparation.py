"""Explicit candidate preparation with real file keys, M6 and isolated PostgreSQL."""
import hashlib
from dataclasses import replace
from datetime import timedelta
from io import StringIO
from pathlib import Path
import secrets
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from data_security.adapters.keys import FileKeyResolver
from data_security.adapters.persistence.models import PrivateObject
from data_security.adapters.persistence.private_store import DjangoPrivateStore
from data_security.application.crypto_service import CryptoService
from data_security.application.private_files import PrivateFilePreparation
from data_security.contracts import (
    BASELINE_LIMITS, CipherEnvelope, Environment, ProtectionError, ReasonCode,
)
from data_security.tests.phase3_fixtures import configuration

from controlled_export.errors import (
    ArtifactIntegrityError, AuthorizationRejected, ContractError, ControlledExportError,
    ExecutionConflict, IdempotencyConflict,
)
from controlled_export.models import (
    DeliveryAttempt, ExecutionAttempt, ExportExecution, OutboxEvent, ProtectedArtifact, ShareGrant,
)
from controlled_export.services import create_share_grant, execute_authorized_export
from controlled_export.transformations import transform

from .helpers import IsolatedStorageMixin, authorization_for, csv_bytes


class PrivateExecutionPreparationTests(IsolatedStorageMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, "postgresql", "requires isolated PostgreSQL")
        files = configuration(providers=())
        config_path, config, refs, _, _ = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        self.root = config_path.parent / "executor-private"
        self.root.mkdir(mode=0o700)
        keys = FileKeyResolver(manifest_path=config["key_manifest"], environment=Environment.EVALUATION,
                               repository_root=Path(__file__).resolve().parents[4])
        self.crypto = CryptoService(keys=keys, service_identity="service/security", random_bytes=secrets.token_bytes,
                                    environment=Environment.EVALUATION, limits=BASELINE_LIMITS)
        self.store = DjangoPrivateStore(root=self.root, crypto=self.crypto, environment=Environment.EVALUATION)
        self.preparation = PrivateFilePreparation(crypto=self.crypto, data_key=refs["data_key"],
                                                 store=self.store, limits=BASELINE_LIMITS)
        self.markers = (b"executor-student@example.invalid", b"192.0.2.74", b"4111111111111111")
        self.content = csv_bytes([["email", "address", "card"], [value.decode() for value in self.markers]])
        self.plan = {"version": "1", "format": "csv", "scope": {"columns": ["email", "address", "card"]},
                     "operations": [{"type": "sanitize_formulas"}]}
        authorization, signature = authorization_for(self.content, self.plan, action="allow")
        self.arguments = dict(authorization=authorization, signature=signature, plan=self.plan,
                              filename="synthetic.csv", content=self.content, idempotency_key="private-1",
                              caller_id="risk-service")
        self.expected = transform(self.content, "synthetic.csv", self.plan, "allow", limits=BASELINE_LIMITS)
        self.prepare = Mock(side_effect=self._prepare)

    def _prepare(self, payload, context):
        self.assertFalse(connection.in_atomic_block)
        self.assertTrue(connection.get_autocommit())
        attempt = ExecutionAttempt.objects.get(pk=context.object_uuid)
        self.assertEqual(attempt.private_candidate["context"], context.to_wire())
        self.assertEqual(attempt.status, "running")
        return self.preparation.prepare(payload, context)

    def _execute(self, **overrides):
        arguments = {**self.arguments, "prepare_private": self.prepare,
                     "private_project_ref": "executor/synthetic", "private_limits": BASELINE_LIMITS, **overrides}
        with patch("controlled_export.services.PrivateStorage", side_effect=AssertionError("legacy storage reached")):
            return execute_authorized_export(**arguments)

    def _assert_unpublished(self, stored):
        context = self.prepare.call_args.args[1]
        self.assertEqual(stored.state, "verified")
        self.assertEqual(self.store.read(stored, context).code, ReasonCode.AUTHORIZATION_DENIED)
        path = self.root / (stored.object_ref.removeprefix("private/") + ".sealed")
        encoded = path.read_bytes()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), stored.ciphertext_hash)
        for marker in self.markers:
            self.assertNotIn(marker, encoded)
        envelope = CipherEnvelope.from_json(encoded)
        opened = self.crypto.open(envelope, context, envelope.key)
        self.assertNotIsInstance(opened, ProtectionError)
        self.assertEqual(hashlib.sha256(opened.binary).hexdigest(), self.expected.output_hash)
        self.assertFalse(any(path.is_file() for path in Path(self._storage_temp.name).rglob("*")))
        self.assertFalse(ProtectedArtifact.objects.exists())
        self.assertFalse(ShareGrant.objects.exists())
        self.assertFalse(DeliveryAttempt.objects.exists())
        self.assertFalse(OutboxEvent.objects.filter(event_type="execution.completed").exists())
        return encoded

    def test_private_preparation_persists_encrypted_candidate_without_delivery(self):
        from data_security.contracts import StoredObject

        receipt, replay = self._execute()
        self.assertFalse(replay)
        self.assertEqual(receipt["status"], "prepared")
        self.assertIsNone(receipt["output_asset_version_id"])
        self.assertIsNone(receipt["output_content_hash"])
        self.assertIsNone(receipt["completed_at"])
        self.assertTrue(all(item["status"] == "not_satisfied" for item in receipt["obligation_results"]))
        attempt = ExecutionAttempt.objects.get()
        self.assertEqual(attempt.status, "prepared")
        self.assertEqual(attempt.candidate_storage_ref, "")
        self.assertEqual(attempt.private_candidate["schema_version"], "controlled-export.private-candidate.v1")
        self.assertEqual(attempt.private_candidate["output_content_hash"], self.expected.output_hash)
        self.assertEqual(attempt.private_candidate["context"]["object_uuid"], str(attempt.attempt_id))
        self._assert_unpublished(StoredObject.from_wire(attempt.private_candidate["stored"]))
        self.assertEqual(PrivateObject.objects.count(), 1)
        self.assertEqual(list(OutboxEvent.objects.values_list("event_type", flat=True)), ["execution.started"])
        # A test-only setting bypasses evaluation's earlier share refusal to exercise the state gate.
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"), self.assertRaises(ExecutionConflict):
            create_share_grant(execution_id=receipt["execution_id"], recipient_id="synthetic-recipient",
                               allowed_operations=["download"], expires_at=timezone.now() + timedelta(minutes=1),
                               idempotency_key="share-private", caller_id="risk-service")
        self.assertFalse(ShareGrant.objects.exists())

    def test_replay_preserves_candidate_and_does_not_prepare_again(self):
        first, _ = self._execute()
        original = ExecutionAttempt.objects.get().private_candidate
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.root.iterdir()}
        second, replay = self._execute()
        self.assertTrue(replay)
        self.assertEqual(first, second)
        self.prepare.assert_called_once()
        self.assertEqual(ExecutionAttempt.objects.get().private_candidate, original)
        self.assertEqual((ExportExecution.objects.count(), ExecutionAttempt.objects.count(), PrivateObject.objects.count()),
                         (1, 1, 1))
        self.assertEqual({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.root.iterdir()}, hashes)

    def test_project_limit_and_legacy_mode_cannot_rebind_the_request(self):
        self._execute()
        for change in ({"private_project_ref": "executor/other"},
                       {"private_limits": replace(BASELINE_LIMITS, max_rows=1000)}):
            with self.subTest(change=tuple(change)), self.assertRaises(IdempotencyConflict):
                self._execute(**change)
        with self.assertRaises(AuthorizationRejected):
            self._execute(prepare_private=None)
        self.prepare.assert_called_once()
        self.assertEqual((ExecutionAttempt.objects.count(), PrivateObject.objects.count()), (1, 1))
        self.assertEqual(ExportExecution.objects.get().state, "prepared")

    def test_admission_rejects_invalid_signature_production_missing_limits_and_outer_transaction(self):
        with self.assertRaises(AuthorizationRejected):
            self._execute(signature="0" * 64)
        authorization, signature = authorization_for(self.content, self.plan, environment="production", action="allow")
        with override_settings(CONTROLLED_EXPORT_ENVIRONMENT="production"), self.assertRaises(AuthorizationRejected) as error:
            self._execute(authorization=authorization, signature=signature)
        self.assertEqual(error.exception.code, "PRIVATE_PREPARATION_ENVIRONMENT")
        with self.assertRaises(ContractError) as error:
            self._execute(private_limits=None)
        self.assertEqual(error.exception.code, "PRIVATE_LIMITS_REQUIRED")
        with transaction.atomic(), self.assertRaises(ExecutionConflict):
            self._execute()
        self.prepare.assert_not_called()
        self.assertFalse(ExportExecution.objects.exists())
        self.assertFalse(PrivateObject.objects.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_stricter_executor_limits_cannot_be_bypassed(self):
        with override_settings(CONTROLLED_EXPORT_MAX_INPUT_BYTES=1024), self.assertRaises(ContractError) as error:
            self._execute()
        self.assertEqual(error.exception.code, "PRIVATE_LIMITS_EXCEEDED")
        self.prepare.assert_not_called()
        self.assertFalse(ExportExecution.objects.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_key_refusal_preserves_attempt_identity_without_success(self):
        refusal = ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
                                  retryable=False, trace_id="executor/key-unavailable")
        with patch.object(self.crypto.keys, "resolve", return_value=refusal), self.assertRaises(ControlledExportError) as error:
            self._execute()
        self.assertEqual(error.exception.code, ReasonCode.KEY_UNAVAILABLE.value)
        attempt = ExecutionAttempt.objects.get()
        self.assertEqual(attempt.status, "unknown")
        self.assertEqual(ExportExecution.objects.get().state, "repair_required")
        self.assertEqual(attempt.private_candidate["context"]["object_uuid"], str(attempt.attempt_id))
        self.assertNotIn("stored", attempt.private_candidate)
        self.assertIsNone(attempt.completed_at)
        self.assertFalse(PrivateObject.objects.exists())
        self.assertFalse(ProtectedArtifact.objects.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_lost_preparation_confirmation_keeps_unknown_and_never_retries(self):
        stored = []

        def lose_confirmation(payload, context):
            stored.append(self.prepare(payload, context))
            raise DatabaseError("synthetic lost preparation confirmation")

        with self.assertRaises(DatabaseError):
            self._execute(prepare_private=lose_confirmation)
        encoded = self._assert_unpublished(stored[0])
        attempt = ExecutionAttempt.objects.get()
        self.assertEqual(attempt.status, "unknown")
        self.assertEqual(ExportExecution.objects.get().state, "repair_required")
        self.assertNotIn("stored", attempt.private_candidate)
        self.assertEqual(list(OutboxEvent.objects.values_list("event_type", flat=True)),
                         ["execution.started", "execution.preparation_unknown"])
        receipt, replay = self._execute()
        self.assertTrue(replay)
        self.assertEqual(receipt["status"], "repair_required")
        self.prepare.assert_called_once()
        self.assertEqual(self._assert_unpublished(stored[0]), encoded)
        self.assertEqual((ExecutionAttempt.objects.count(), PrivateObject.objects.count()), (1, 1))

    def test_committed_preparation_survives_real_commit_confirmation_loss(self):
        from data_security.contracts import StoredObject

        commit = connection.commit
        lost = False

        def commit_then_lose():
            nonlocal lost
            should_lose = not lost and ExportExecution.objects.filter(state="prepared").exists()
            result = commit()
            if should_lose:
                lost = True
                raise DatabaseError("synthetic confirmation lost after real commit")
            return result

        with patch.object(connection, "commit", side_effect=commit_then_lose), self.assertRaisesRegex(
            DatabaseError, "^synthetic confirmation lost after real commit$"
        ):
            self._execute()
        self.assertTrue(lost)
        self.assertEqual(ExportExecution.objects.get().state, "prepared")
        attempt = ExecutionAttempt.objects.get()
        self.assertEqual(attempt.status, "prepared")
        encoded = self._assert_unpublished(StoredObject.from_wire(attempt.private_candidate["stored"]))
        receipt, replay = self._execute()
        self.assertTrue(replay)
        self.assertEqual(receipt["status"], "prepared")
        self.prepare.assert_called_once()
        self.assertEqual(self._assert_unpublished(StoredObject.from_wire(attempt.private_candidate["stored"])), encoded)
        self.assertEqual((ExecutionAttempt.objects.count(), PrivateObject.objects.count()), (1, 1))

    def test_expiry_after_preparation_keeps_unpublished_ciphertext(self):
        for field in ("authorization", "lease"):
            with self.subTest(field=field):
                authorization, signature = authorization_for(self.content, self.plan, action="allow")
                stored = []

                def expire(payload, context):
                    stored.append(self.prepare(payload, context))
                    past = timezone.now() - timedelta(seconds=1)
                    if field == "authorization":
                        ExportExecution.objects.filter(pk=authorization["execution_id"]).update(valid_until=past)
                    else:
                        ExecutionAttempt.objects.filter(pk=context.object_uuid).update(lease_expires_at=past)
                    return stored[0]

                with self.assertRaises(ExecutionConflict):
                    self._execute(authorization=authorization, signature=signature,
                                  idempotency_key="expire-" + field, prepare_private=expire)
                self._assert_unpublished(stored[0])
                execution = ExportExecution.objects.get(pk=authorization["execution_id"])
                self.assertEqual(execution.state, "repair_required")
                self.assertEqual(execution.attempts.get().status, "unknown")
                self.assertNotIn("stored", execution.attempts.get().private_candidate)

    def test_expired_private_attempt_keeps_unknown_and_ciphertext(self):
        stored = []

        def interrupt(payload, context):
            stored.append(self.prepare(payload, context))
            raise SystemExit("synthetic worker interruption")

        with self.assertRaises(SystemExit):
            self._execute(prepare_private=interrupt)
        attempt = ExecutionAttempt.objects.get()
        self.assertEqual(attempt.status, "running")
        intent = attempt.private_candidate
        encoded = self._assert_unpublished(stored[0])
        ExecutionAttempt.objects.filter(pk=attempt.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        output = StringIO()
        call_command("expire_stale_attempts", stdout=output)
        self.assertEqual(output.getvalue().strip(), "fenced_attempts=1")
        attempt.refresh_from_db()
        execution = ExportExecution.objects.get()
        self.assertEqual((attempt.status, execution.state), ("unknown", "repair_required"))
        self.assertIsNone(attempt.completed_at)
        self.assertIsNone(execution.completed_at)
        self.assertEqual(attempt.private_candidate, intent)
        self.assertEqual(list(OutboxEvent.objects.values_list("event_type", flat=True)),
                         ["execution.started", "execution.preparation_unknown"])
        repeated = StringIO()
        call_command("expire_stale_attempts", stdout=repeated)
        self.assertEqual(repeated.getvalue().strip(), "fenced_attempts=0")
        receipt, replay = self._execute()
        self.assertTrue(replay)
        self.assertEqual(receipt["status"], "repair_required")
        self.prepare.assert_called_once()
        self.assertEqual(self._assert_unpublished(stored[0]), encoded)
        self.assertEqual((ExecutionAttempt.objects.count(), PrivateObject.objects.count(), OutboxEvent.objects.count()),
                         (1, 1, 2))

    def test_expired_legacy_attempt_preserves_original_failure_semantics(self):
        with patch("controlled_export.services.transform", side_effect=SystemExit("synthetic worker interruption")):
            with self.assertRaises(SystemExit):
                execute_authorized_export(**self.arguments)
        attempt = ExecutionAttempt.objects.get()
        self.assertEqual(attempt.status, "running")
        self.assertEqual(attempt.private_candidate, {})
        ExecutionAttempt.objects.filter(pk=attempt.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        output = StringIO()
        call_command("expire_stale_attempts", stdout=output)
        self.assertEqual(output.getvalue().strip(), "fenced_attempts=1")
        attempt.refresh_from_db()
        execution = ExportExecution.objects.get()
        self.assertEqual((attempt.status, execution.state), ("stale", "failed"))
        self.assertIsNotNone(attempt.completed_at)
        self.assertIsNotNone(execution.completed_at)
        self.assertEqual(attempt.error_code, "LEASE_EXPIRED")
        self.assertEqual(execution.error_code, "LEASE_EXPIRED_RECONCILIATION_REQUIRED")
        self.assertEqual(list(OutboxEvent.objects.values_list("event_type", flat=True)),
                         ["execution.started", "execution.failed"])
        self.prepare.assert_not_called()
        self.assertFalse(PrivateObject.objects.exists())
        self.assertFalse(ProtectedArtifact.objects.exists())

    def test_changed_fence_cannot_register_private_preparation(self):
        stored = []

        def fence(payload, context):
            stored.append(self.prepare(payload, context))
            ExportExecution.objects.filter(pk=self.arguments["authorization"]["execution_id"]).update(fencing_token=2)
            return stored[0]

        with self.assertRaises(ExecutionConflict):
            self._execute(prepare_private=fence)
        self._assert_unpublished(stored[0])
        execution = ExportExecution.objects.get()
        self.assertEqual((execution.state, execution.fencing_token), ("running", 2))
        self.assertEqual(ExecutionAttempt.objects.get().status, "running")
        self.assertNotIn("stored", ExecutionAttempt.objects.get().private_candidate)
        self.assertFalse(OutboxEvent.objects.filter(event_type="execution.preparation_unknown").exists())

    def test_wrong_preparation_state_cannot_create_an_artifact(self):
        stored = []

        def invalid_state(payload, context):
            stored.append(self.prepare(payload, context))
            return replace(stored[0], state="published")

        with self.assertRaises(ArtifactIntegrityError):
            self._execute(prepare_private=invalid_state)
        self._assert_unpublished(stored[0])
        self.assertEqual(ExportExecution.objects.get().state, "repair_required")
        self.assertEqual(ExecutionAttempt.objects.get().status, "unknown")
        self.assertNotIn("stored", ExecutionAttempt.objects.get().private_candidate)
