import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .authorization import (
    digest_json,
    execution_request_fingerprint,
    receipt_obligation_ids,
    sha256_bytes,
    share_creation_constraints,
    validate_authorization,
)
from .errors import (
    ArtifactIntegrityError,
    AuthorizationRejected,
    ContractError,
    ControlledExportError,
    ExecutionConflict,
    IdempotencyConflict,
    ShareAccessDenied,
)
from .models import (
    DeliveryAttempt,
    ExecutionAttempt,
    ExportExecution,
    IdempotencyRecord,
    OutboxEvent,
    ProtectedArtifact,
    ShareGrant,
)
from .storage import PrivateStorage
from .transformations import transform


IDEMPOTENCY_RETENTION = timedelta(days=7)
ALLOWED_SHARE_OPERATIONS = {"preview", "download"}


def _outbox(aggregate_type, aggregate_id, event_type, payload, version=1):
    forbidden = {"token", "token_digest", "private_storage_ref", "content", "secret"}
    if forbidden.intersection(payload):
        raise ContractError("Outbox payload contains a forbidden field", code="OUTBOX_DATA_REJECTED")
    return OutboxEvent.objects.create(
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        aggregate_version=version,
        event_type=event_type,
        payload=payload,
    )


def _idempotency(
    *,
    environment,
    data_domain,
    caller_id,
    operation,
    key,
    fingerprint,
):
    if not isinstance(key, str) or not key.strip() or len(key) > 200:
        raise ContractError("A bounded idempotency key is required", code="IDEMPOTENCY_KEY_INVALID")
    record, created = IdempotencyRecord.objects.select_for_update().get_or_create(
        environment=environment,
        data_domain=data_domain,
        caller_id=caller_id,
        operation=operation,
        idempotency_key=key.strip(),
        defaults={
            "request_fingerprint": fingerprint,
            "expires_at": timezone.now() + IDEMPOTENCY_RETENTION,
        },
    )
    if not created and record.request_fingerprint != fingerprint:
        raise IdempotencyConflict("Idempotency key was reused with different content")
    return record, created


def execution_receipt(execution):
    artifact = getattr(execution, "artifact", None)
    attempt = execution.attempts.order_by("-attempt_no").first()
    return {
        "result_id": str(execution.execution_id),
        "execution_id": str(execution.execution_id),
        "attempt_id": str(attempt.attempt_id) if attempt else None,
        "status": execution.state,
        "effective_action": execution.effective_action,
        "input_asset_version_id": execution.asset_version_id,
        "output_asset_version_id": str(artifact.output_asset_version_id) if artifact else None,
        "output_content_hash": artifact.output_content_hash if artifact else None,
        "obligation_results": [
            {
                "obligation_id": obligation["obligation_id"],
                "status": "satisfied" if execution.state == "succeeded" else "not_satisfied",
            }
            for obligation in execution.obligations
            if obligation["phase"] == "before_publish"
        ],
        "processed_record_count": artifact.processed_record_count if artifact else None,
        "output_record_count": artifact.output_record_count if artifact else None,
        "error_code": execution.error_code or None,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        "evidence_refs": [str(event.event_id) for event in OutboxEvent.objects.filter(
            aggregate_type="execution", aggregate_id=str(execution.execution_id)
        ).order_by("created_at")],
    }


def _claim_execution(execution):
    locked = ExportExecution.objects.select_for_update().get(pk=execution.pk)
    if locked.state != "queued":
        raise ExecutionConflict(f"Execution cannot be claimed from {locked.state}")
    locked.fencing_token += 1
    attempt_no = locked.attempts.count() + 1
    now = timezone.now()
    attempt = ExecutionAttempt.objects.create(
        execution=locked,
        attempt_no=attempt_no,
        fencing_token=locked.fencing_token,
        lease_expires_at=now + timedelta(seconds=settings.CONTROLLED_EXPORT_LEASE_SECONDS),
    )
    locked.state = "running"
    locked.active_attempt_id = attempt.attempt_id
    locked.started_at = now
    locked.save(update_fields=["state", "active_attempt_id", "fencing_token", "started_at", "updated_at"])
    _outbox(
        "execution",
        locked.execution_id,
        "execution.started",
        {
            "execution_id": str(locked.execution_id),
            "attempt_id": str(attempt.attempt_id),
            "environment": locked.environment,
            "data_domain": locked.data_domain,
        },
        locked.fencing_token,
    )
    return attempt


def _fail_execution(execution_id, attempt_id, fencing_token, error_code):
    with transaction.atomic():
        execution = ExportExecution.objects.select_for_update().get(pk=execution_id)
        if execution.active_attempt_id != attempt_id or execution.fencing_token != fencing_token:
            return
        if execution.state not in {"running", "queued"}:
            return
        now = timezone.now()
        attempt = ExecutionAttempt.objects.select_for_update().get(pk=attempt_id)
        attempt.status = "failed"
        attempt.error_code = error_code
        attempt.completed_at = now
        attempt.save(update_fields=["status", "error_code", "completed_at"])
        execution.state = "failed"
        execution.error_code = error_code
        execution.completed_at = now
        execution.save(update_fields=["state", "error_code", "completed_at", "updated_at"])
        _outbox(
            "execution",
            execution.execution_id,
            "execution.failed",
            {
                "execution_id": str(execution.execution_id),
                "attempt_id": str(attempt.attempt_id),
                "error_code": error_code,
            },
            execution.fencing_token,
        )


def execute_authorized_export(*, authorization, signature, plan, filename, content, idempotency_key, caller_id):
    validated = validate_authorization(authorization, signature)
    payload = validated.payload
    actual_input_hash = sha256_bytes(content)
    if not hmac.compare_digest(actual_input_hash, payload["input_content_hash"]):
        raise AuthorizationRejected("Input bytes do not match the authorization", code="INPUT_HASH_MISMATCH")
    plan_hash = digest_json(plan)
    authorized_plan_hash = payload.get("plan_hash", "")
    if authorized_plan_hash and not hmac.compare_digest(plan_hash, authorized_plan_hash):
        raise AuthorizationRejected("Plan does not match the authorization", code="PLAN_HASH_MISMATCH")
    request_fingerprint = execution_request_fingerprint(
        payload,
        actual_input_hash=actual_input_hash,
        plan_hash=plan_hash,
        caller_id=caller_id,
    )
    if not hmac.compare_digest(request_fingerprint, payload["request_fingerprint"]):
        raise AuthorizationRejected("Request fingerprint mismatch", code="REQUEST_FINGERPRINT_MISMATCH")

    with transaction.atomic():
        idem, created = _idempotency(
            environment=payload["environment"],
            data_domain=payload["data_domain"],
            caller_id=caller_id,
            operation="execute_authorized_export",
            key=idempotency_key,
            fingerprint=request_fingerprint,
        )
        if not created:
            if not idem.result_id:
                raise ExecutionConflict("An incomplete idempotency record requires reconciliation")
            existing = ExportExecution.objects.get(pk=idem.result_id)
            return execution_receipt(existing), True
        try:
            execution = ExportExecution.objects.create(
                execution_id=payload["execution_id"],
                authorization_id=payload["authorization_id"],
                export_request_id=payload["export_request_id"],
                decision_id=payload["decision_id"],
                asset_version_id=payload["asset_version_id"],
                input_content_hash=actual_input_hash,
                profile_id=payload["profile_id"],
                request_fingerprint=request_fingerprint,
                scope_hash=payload["scope_hash"],
                effective_action=payload["effective_action"],
                obligations=validated.obligations,
                plan_id=payload.get("plan_id", ""),
                plan_hash=plan_hash,
                reservation_id=payload.get("reservation_id", ""),
                valid_until=validated.valid_until,
                environment=payload["environment"],
                data_domain=payload["data_domain"],
                subject_id=payload["subject_id"],
            )
        except (IntegrityError, ValueError) as exc:
            raise AuthorizationRejected(
                "Execution authorization has already been consumed or has an invalid identifier",
                code="AUTHORIZATION_ALREADY_CONSUMED",
            ) from exc
        idem.result_type = "ExportExecution"
        idem.result_id = str(execution.execution_id)
        idem.save(update_fields=["result_type", "result_id"])
        attempt = _claim_execution(execution)

    storage = PrivateStorage()
    finalized_reference = None
    try:
        result = transform(content, filename, plan, payload["effective_action"])
        if not hmac.compare_digest(result.scope_hash, payload["scope_hash"]):
            raise AuthorizationRejected("Plan scope does not match the authorization", code="SCOPE_HASH_MISMATCH")
        candidate = storage.write_candidate(
            str(execution.execution_id), str(attempt.attempt_id), result.suffix, result.content
        )
        with transaction.atomic():
            current = ExportExecution.objects.select_for_update().get(pk=execution.pk)
            current_attempt = ExecutionAttempt.objects.select_for_update().get(pk=attempt.pk)
            if (
                current.state != "running"
                or current.active_attempt_id != attempt.attempt_id
                or current.fencing_token != attempt.fencing_token
                or current_attempt.status != "running"
            ):
                raise ExecutionConflict("A stale worker cannot register a candidate")
            current_attempt.candidate_storage_ref = candidate
            current_attempt.save(update_fields=["candidate_storage_ref"])

        output_id = uuid.uuid4()
        finalized_reference = storage.finalize_candidate(
            candidate, str(execution.execution_id), str(output_id), result.suffix
        )
        if not hmac.compare_digest(storage.sha256(finalized_reference), result.output_hash):
            raise ArtifactIntegrityError("Finalized artifact changed before registration")

        with transaction.atomic():
            current = ExportExecution.objects.select_for_update().get(pk=execution.pk)
            current_attempt = ExecutionAttempt.objects.select_for_update().get(pk=attempt.pk)
            if (
                current.state != "running"
                or current.active_attempt_id != attempt.attempt_id
                or current.fencing_token != attempt.fencing_token
                or current_attempt.status != "running"
            ):
                raise ExecutionConflict("A stale worker cannot register an artifact")
            artifact = ProtectedArtifact.objects.create(
                output_asset_version_id=output_id,
                execution=current,
                attempt=current_attempt,
                source_asset_version_id=current.asset_version_id,
                private_storage_ref=finalized_reference,
                output_content_hash=result.output_hash,
                output_format=result.output_format,
                scope_hash=result.scope_hash,
                plan_hash=result.plan_hash,
                validation_status="passed",
                processed_record_count=result.processed_records,
                output_record_count=result.output_records,
            )
            now = timezone.now()
            current_attempt.status = "succeeded"
            current_attempt.completed_at = now
            current_attempt.save(update_fields=["status", "completed_at"])
            current.state = "succeeded"
            current.completed_at = now
            current.save(update_fields=["state", "completed_at", "updated_at"])
            _outbox(
                "execution",
                current.execution_id,
                "execution.completed",
                {
                    "execution_id": str(current.execution_id),
                    "attempt_id": str(current_attempt.attempt_id),
                    "output_asset_version_id": str(artifact.output_asset_version_id),
                    "output_content_hash": artifact.output_content_hash,
                    "processed_record_count": artifact.processed_record_count,
                    "output_record_count": artifact.output_record_count,
                },
                current.fencing_token,
            )
        current.refresh_from_db()
        return execution_receipt(current), False
    except Exception as exc:
        error_code = getattr(exc, "code", "EXECUTION_FAILED")
        _fail_execution(execution.execution_id, attempt.attempt_id, attempt.fencing_token, error_code)
        raise


def _token_digest(token):
    pepper = settings.SHARE_TOKEN_PEPPER
    if not pepper:
        raise ContractError("Share token pepper is not configured", code="TOKEN_PROVIDER_UNAVAILABLE")
    return hmac.new(pepper.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def _new_token():
    token = secrets.token_urlsafe(32)
    return token, _token_digest(token)


def _share_violates_obligations(share, execution):
    try:
        recipient_id, expiry_limit = share_creation_constraints(execution.obligations)
    except ControlledExportError:
        return True
    if recipient_id is not None and share.recipient_id != recipient_id:
        return True
    if expiry_limit is not None and share.expires_at > expiry_limit:
        return True
    return False


def create_share_grant(
    *,
    execution_id,
    recipient_id,
    allowed_operations,
    expires_at,
    idempotency_key,
    caller_id,
):
    if settings.CONTROLLED_EXPORT_ENVIRONMENT == "evaluation":
        raise AuthorizationRejected("Evaluation mode cannot create shares", code="EVALUATION_SHARE_FORBIDDEN")
    operations = sorted(set(allowed_operations or []))
    if not operations or not set(operations).issubset(ALLOWED_SHARE_OPERATIONS):
        raise ContractError("Share operations are invalid", code="SHARE_OPERATIONS_INVALID")
    if not isinstance(recipient_id, str) or not recipient_id.strip() or len(recipient_id.strip()) > 160:
        raise ContractError("Recipient identifier is invalid", code="RECIPIENT_INVALID")
    recipient_id = recipient_id.strip()
    now = timezone.now()
    if expires_at.utcoffset() is None or not (now < expires_at <= now + timedelta(seconds=settings.CONTROLLED_EXPORT_MAX_SHARE_SECONDS)):
        raise ContractError("Share expiry is outside the approved window", code="SHARE_EXPIRY_INVALID")
    fingerprint = digest_json(
        {
            "execution_id": str(execution_id),
            "recipient_id": recipient_id,
            "allowed_operations": operations,
            "expires_at": expires_at.isoformat(),
        }
    )
    token, digest = _new_token()
    with transaction.atomic():
        execution = ExportExecution.objects.select_for_update().select_related("artifact").get(pk=execution_id)
        now = timezone.now()
        if execution.state != "succeeded":
            raise ExecutionConflict("Only a succeeded execution can be shared")
        if execution.environment != settings.CONTROLLED_EXPORT_ENVIRONMENT:
            raise AuthorizationRejected("Execution environment mismatch", code="ENVIRONMENT_MISMATCH")
        if now >= execution.valid_until:
            raise AuthorizationRejected("Execution authorization must be revalidated", code="AUTHORIZATION_EXPIRED")
        bound_recipient, expiry_limit = share_creation_constraints(execution.obligations)
        if bound_recipient is not None and recipient_id != bound_recipient:
            raise AuthorizationRejected(
                "Share recipient does not match the signed obligation",
                code="RECIPIENT_OBLIGATION_MISMATCH",
            )
        if expiry_limit is not None and expires_at > expiry_limit:
            raise ContractError(
                "Share expiry exceeds the signed obligation",
                code="SHARE_EXPIRY_OBLIGATION_EXCEEDED",
            )
        idem, created = _idempotency(
            environment=execution.environment,
            data_domain=execution.data_domain,
            caller_id=caller_id,
            operation="create_share_grant",
            key=idempotency_key,
            fingerprint=fingerprint,
        )
        if not created:
            if not idem.result_id:
                raise ExecutionConflict("An incomplete share idempotency record requires reconciliation")
            existing = ShareGrant.objects.get(pk=idem.result_id)
            if _share_violates_obligations(existing, execution):
                raise AuthorizationRejected(
                    "Existing share does not satisfy the signed obligations",
                    code="SHARE_OBLIGATION_MISMATCH",
                )
            if existing.revoked_at is not None or now >= existing.expires_at:
                raise AuthorizationRejected(
                    "Existing share is no longer active",
                    code="SHARE_INACTIVE",
                )
            return existing, None, True
        share = ShareGrant.objects.create(
            execution=execution,
            artifact=execution.artifact,
            recipient_id=recipient_id,
            allowed_operations=operations,
            expires_at=expires_at,
            token_digest=digest,
            environment=execution.environment,
            data_domain=execution.data_domain,
        )
        idem.result_type = "ShareGrant"
        idem.result_id = str(share.share_id)
        idem.save(update_fields=["result_type", "result_id"])
        _outbox(
            "share",
            share.share_id,
            "share.created",
            {
                "share_id": str(share.share_id),
                "execution_id": str(execution.execution_id),
                "output_asset_version_id": str(execution.artifact.output_asset_version_id),
                "recipient_id": share.recipient_id,
                "allowed_operations": operations,
                "expires_at": share.expires_at.isoformat(),
            },
            share.grant_version,
        )
    return share, token, False


def rotate_share_token(*, share_id, caller_id):
    token, digest = _new_token()
    with transaction.atomic():
        share = ShareGrant.objects.select_for_update().select_related("execution").get(pk=share_id)
        if share.revoked_at is not None or timezone.now() >= share.expires_at:
            raise ShareAccessDenied("An inactive share cannot rotate tokens")
        if _share_violates_obligations(share, share.execution):
            raise ShareAccessDenied("Share does not satisfy the signed obligations")
        share.token_digest = digest
        share.grant_version += 1
        share.save(update_fields=["token_digest", "grant_version", "updated_at"])
        _outbox(
            "share",
            share.share_id,
            "share.token_rotated",
            {"share_id": str(share.share_id), "rotated_by": caller_id},
            share.grant_version,
        )
    return share, token


def revoke_share_grant(*, share_id, caller_id):
    with transaction.atomic():
        share = ShareGrant.objects.select_for_update().get(pk=share_id)
        if share.revoked_at is not None:
            return share, True
        share.revoked_at = timezone.now()
        share.grant_version += 1
        share.save(update_fields=["revoked_at", "grant_version", "updated_at"])
        _outbox(
            "share",
            share.share_id,
            "share.revoked",
            {
                "share_id": str(share.share_id),
                "revoked_by": caller_id,
                "revoked_at": share.revoked_at.isoformat(),
            },
            share.grant_version,
        )
    return share, False


def _mark_integrity_failure(execution_id, code):
    with transaction.atomic():
        execution = ExportExecution.objects.select_for_update().get(pk=execution_id)
        if execution.state != "repair_required":
            execution.state = "repair_required"
            execution.error_code = code
            execution.save(update_fields=["state", "error_code", "updated_at"])
            _outbox(
                "execution",
                execution.execution_id,
                "artifact.integrity_failed",
                {"execution_id": str(execution.execution_id), "error_code": code},
                execution.fencing_token,
            )


def authorize_share_access(*, share_id, recipient_id, token, operation):
    if operation not in ALLOWED_SHARE_OPERATIONS:
        raise ShareAccessDenied("Unsupported share operation")
    if not isinstance(token, str) or not token:
        raise ShareAccessDenied("Share token is required")
    digest = _token_digest(token)
    snapshot = ShareGrant.objects.select_related("artifact", "execution").get(pk=share_id)
    try:
        PrivateStorage().ensure_integrity(
            snapshot.artifact.private_storage_ref,
            snapshot.artifact.output_content_hash,
        )
    except ArtifactIntegrityError as exc:
        _mark_integrity_failure(snapshot.execution_id, exc.code)
        raise ShareAccessDenied("Artifact is unavailable pending repair") from exc

    denied = False
    delivery = None
    with transaction.atomic():
        share = (
            ShareGrant.objects.select_for_update()
            .select_related("artifact", "execution")
            .get(pk=share_id)
        )
        now = timezone.now()
        denied = (
            share.revoked_at is not None
            or now >= share.expires_at
            or share.recipient_id != str(recipient_id)
            or operation not in share.allowed_operations
            or share.environment != settings.CONTROLLED_EXPORT_ENVIRONMENT
            or share.execution.state != "succeeded"
            or not hmac.compare_digest(share.token_digest, digest)
            or _share_violates_obligations(share, share.execution)
        )
        if denied:
            _outbox(
                "share",
                share.share_id,
                "share.access_denied",
                {
                    "share_id": str(share.share_id),
                    "recipient_id": str(recipient_id),
                    "operation": operation,
                },
                share.grant_version,
            )
        else:
            delivery = DeliveryAttempt.objects.create(
                share=share,
                execution=share.execution,
                recipient_id=str(recipient_id),
                operation=operation,
                actual_content_hash=share.artifact.output_content_hash,
                admitted_at=now,
            )
            _outbox(
                "delivery",
                delivery.delivery_id,
                "share.accessed",
                {
                    "delivery_id": str(delivery.delivery_id),
                    "share_id": str(share.share_id),
                    "execution_id": str(share.execution_id),
                    "recipient_id": delivery.recipient_id,
                    "operation": operation,
                    "admitted_at": now.isoformat(),
                },
            )
    if denied:
        raise ShareAccessDenied("Share access was denied")
    return delivery, share.artifact


def _delivery_transition(delivery_id, status, *, bytes_sent=None, error_code="", measurement_basis=""):
    with transaction.atomic():
        delivery = (
            DeliveryAttempt.objects.select_for_update()
            .select_related("execution")
            .get(pk=delivery_id)
        )
        now = timezone.now()
        if status == "started":
            if delivery.status != "not_started":
                return delivery
            delivery.status = "started"
            delivery.response_started_at = now
            event_type = "delivery.started"
            fields = ["status", "response_started_at"]
            payload = {
                "delivery_id": str(delivery.delivery_id),
                "share_id": str(delivery.share_id),
                "status": delivery.status,
                "bytes_sent": delivery.bytes_sent,
                "measurement_basis": delivery.measurement_basis,
                "error_code": delivery.error_code,
            }
        else:
            if delivery.status in {"completed", "failed"}:
                return delivery
            obligation_ids = receipt_obligation_ids(delivery.execution.obligations)
            delivery.status = status
            delivery.bytes_sent = bytes_sent
            delivery.measurement_basis = measurement_basis
            delivery.error_code = error_code
            delivery.completed_at = now
            event_type = f"delivery.{status}"
            fields = ["status", "bytes_sent", "measurement_basis", "error_code", "completed_at"]
            payload = {
                "delivery_id": str(delivery.delivery_id),
                "share_id": str(delivery.share_id),
                "status": delivery.status,
                "bytes_sent": delivery.bytes_sent,
                "measurement_basis": delivery.measurement_basis,
                "error_code": delivery.error_code,
                "obligation_ids": obligation_ids,
                "evidence_ref": None,
            }
        delivery.save(update_fields=fields)
        _outbox(
            "delivery",
            delivery.delivery_id,
            event_type,
            payload,
        )
        return delivery


def stream_delivery(delivery, artifact, chunk_size=64 * 1024):
    storage = PrivateStorage()
    sent = 0
    _delivery_transition(delivery.delivery_id, "started")
    try:
        with storage.open(artifact.private_storage_ref) as handle:
            for chunk in iter(lambda: handle.read(chunk_size), b""):
                sent += len(chunk)
                yield chunk
    except GeneratorExit:
        _delivery_transition(
            delivery.delivery_id,
            "unknown",
            bytes_sent=sent,
            measurement_basis="stream_closed_without_client_ack",
        )
        raise
    except Exception:
        _delivery_transition(
            delivery.delivery_id,
            "failed",
            bytes_sent=sent,
            error_code="STREAM_FAILED",
            measurement_basis="server_stream_error",
        )
        raise
    else:
        _delivery_transition(
            delivery.delivery_id,
            "unknown",
            bytes_sent=sent,
            measurement_basis="server_stream_exhausted_no_client_ack",
        )


def record_delivery_result(*, delivery_id, status, bytes_sent, evidence_ref):
    if status not in {"completed", "failed", "unknown"}:
        raise ContractError("Delivery result status is invalid", code="DELIVERY_STATUS_INVALID")
    if status == "completed" and (bytes_sent is None or not evidence_ref):
        raise ContractError("Completed delivery requires byte count and evidence", code="DELIVERY_EVIDENCE_REQUIRED")
    with transaction.atomic():
        delivery = (
            DeliveryAttempt.objects.select_for_update()
            .select_related("execution")
            .get(pk=delivery_id)
        )
        if delivery.status in {"completed", "failed"}:
            if delivery.status == status and delivery.bytes_sent == bytes_sent:
                return delivery, True
            raise ExecutionConflict("Delivery has an immutable terminal result")
        obligation_ids = receipt_obligation_ids(delivery.execution.obligations)
        delivery.status = status
        delivery.bytes_sent = bytes_sent
        delivery.measurement_basis = f"external_receipt:{evidence_ref}"[:120]
        delivery.completed_at = timezone.now()
        delivery.save(update_fields=["status", "bytes_sent", "measurement_basis", "completed_at"])
        _outbox(
            "delivery",
            delivery.delivery_id,
            f"delivery.{status}",
            {
                "delivery_id": str(delivery.delivery_id),
                "share_id": str(delivery.share_id),
                "status": status,
                "bytes_sent": bytes_sent,
                "evidence_ref": evidence_ref,
                "obligation_ids": obligation_ids,
            },
        )
    return delivery, False
