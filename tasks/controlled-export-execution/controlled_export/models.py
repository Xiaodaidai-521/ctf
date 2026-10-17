import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class ExportExecution(models.Model):
    STATE = [
        ("queued", "queued"),
        ("running", "running"),
        ("succeeded", "succeeded"),
        ("failed", "failed"),
        ("cancelled", "cancelled"),
        ("repair_required", "repair_required"),
    ]

    execution_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    authorization_id = models.CharField(max_length=160, unique=True)
    export_request_id = models.CharField(max_length=160)
    decision_id = models.CharField(max_length=160)
    asset_version_id = models.CharField(max_length=160)
    input_content_hash = models.CharField(max_length=64)
    profile_id = models.CharField(max_length=160)
    request_fingerprint = models.CharField(max_length=64)
    scope_hash = models.CharField(max_length=64)
    effective_action = models.CharField(max_length=24)
    obligations = models.JSONField(default=list)
    plan_id = models.CharField(max_length=160, blank=True)
    plan_hash = models.CharField(max_length=64, blank=True)
    reservation_id = models.CharField(max_length=160, blank=True)
    valid_until = models.DateTimeField()
    environment = models.CharField(max_length=40)
    data_domain = models.CharField(max_length=120)
    subject_id = models.CharField(max_length=160)
    state = models.CharField(max_length=24, choices=STATE, default="queued", db_index=True)
    fencing_token = models.PositiveBigIntegerField(default=0)
    active_attempt_id = models.UUIDField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["environment", "data_domain", "state"], name="ce_exec_scope_state"),
            models.Index(fields=["valid_until"], name="ce_exec_valid_until"),
        ]


class ExecutionAttempt(models.Model):
    STATUS = [
        ("running", "running"),
        ("succeeded", "succeeded"),
        ("failed", "failed"),
        ("cancelled", "cancelled"),
        ("stale", "stale"),
    ]

    attempt_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(ExportExecution, on_delete=models.PROTECT, related_name="attempts")
    attempt_no = models.PositiveIntegerField()
    fencing_token = models.PositiveBigIntegerField()
    lease_expires_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS, default="running", db_index=True)
    candidate_storage_ref = models.CharField(max_length=500, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["execution", "attempt_no"], name="ce_unique_attempt_no"),
            models.UniqueConstraint(fields=["execution", "fencing_token"], name="ce_unique_fence"),
        ]
        indexes = [models.Index(fields=["status", "lease_expires_at"], name="ce_attempt_lease")]


class ProtectedArtifact(models.Model):
    output_asset_version_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.OneToOneField(ExportExecution, on_delete=models.PROTECT, related_name="artifact")
    attempt = models.ForeignKey(ExecutionAttempt, on_delete=models.PROTECT, related_name="artifacts")
    source_asset_version_id = models.CharField(max_length=160)
    private_storage_ref = models.CharField(max_length=500, unique=True)
    output_content_hash = models.CharField(max_length=64)
    output_format = models.CharField(max_length=12)
    scope_hash = models.CharField(max_length=64)
    plan_hash = models.CharField(max_length=64, blank=True)
    validation_status = models.CharField(max_length=24, default="passed")
    processed_record_count = models.PositiveBigIntegerField(null=True, blank=True)
    output_record_count = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk and ProtectedArtifact.objects.filter(pk=self.pk).exists():
            raise ValidationError("ProtectedArtifact records are immutable")
        return super().save(*args, **kwargs)


class ShareGrant(models.Model):
    share_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(ExportExecution, on_delete=models.PROTECT, related_name="shares")
    artifact = models.ForeignKey(ProtectedArtifact, on_delete=models.PROTECT, related_name="shares")
    recipient_id = models.CharField(max_length=160, db_index=True)
    allowed_operations = models.JSONField(default=list)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    grant_version = models.PositiveBigIntegerField(default=1)
    token_digest = models.CharField(max_length=64, unique=True)
    environment = models.CharField(max_length=40)
    data_domain = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="ce_share_expiry_after_create",
            )
        ]
        indexes = [
            models.Index(fields=["recipient_id", "expires_at"], name="ce_share_recipient"),
            models.Index(fields=["environment", "data_domain"], name="ce_share_scope"),
        ]


class DeliveryAttempt(models.Model):
    STATUS = [
        ("not_started", "not_started"),
        ("started", "started"),
        ("completed", "completed"),
        ("failed", "failed"),
        ("unknown", "unknown"),
    ]

    delivery_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    share = models.ForeignKey(ShareGrant, on_delete=models.PROTECT, related_name="deliveries")
    execution = models.ForeignKey(ExportExecution, on_delete=models.PROTECT, related_name="deliveries")
    recipient_id = models.CharField(max_length=160)
    operation = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS, default="not_started", db_index=True)
    actual_content_hash = models.CharField(max_length=64)
    bytes_sent = models.PositiveBigIntegerField(null=True, blank=True)
    delivered_record_count = models.PositiveBigIntegerField(null=True, blank=True)
    measurement_basis = models.CharField(max_length=120, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    admitted_at = models.DateTimeField()
    response_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["share", "admitted_at"], name="ce_delivery_share_time"),
            models.Index(fields=["status", "admitted_at"], name="ce_delivery_status_time"),
        ]


class IdempotencyRecord(models.Model):
    environment = models.CharField(max_length=40)
    data_domain = models.CharField(max_length=120)
    caller_id = models.CharField(max_length=160)
    operation = models.CharField(max_length=80)
    idempotency_key = models.CharField(max_length=200)
    request_fingerprint = models.CharField(max_length=64)
    result_type = models.CharField(max_length=80, blank=True)
    result_id = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["environment", "data_domain", "caller_id", "operation", "idempotency_key"],
                name="ce_idempotency_scope",
            )
        ]
        indexes = [models.Index(fields=["expires_at"], name="ce_idem_expiry")]


class OutboxEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aggregate_type = models.CharField(max_length=80)
    aggregate_id = models.CharField(max_length=160)
    aggregate_version = models.PositiveBigIntegerField(default=1)
    event_type = models.CharField(max_length=120)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    publish_attempts = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["published_at", "created_at"], name="ce_outbox_pending"),
            models.Index(fields=["aggregate_type", "aggregate_id"], name="ce_outbox_aggregate"),
        ]
