from django.db import models

from .canary_catalog import CanaryRegistration


class PolicyVersion(models.Model):
    version = models.CharField(max_length=128, unique=True)
    document = models.JSONField()

    class Meta:
        ordering = ('id',)


class QuotaExecution(models.Model):
    """Flow binding and effect receipts, not a second quota balance authority."""
    idempotency_key = models.CharField(max_length=160, unique=True)
    reservation_id = models.CharField(max_length=160, unique=True)
    binding_hash = models.CharField(max_length=64)
    terminal_operation = models.CharField(max_length=16, blank=True)
    terminal_receipt = models.JSONField(null=True)
    unknown_receipt = models.JSONField(null=True)


class PrivateObject(models.Model):
    """Immutable ciphertext identity; publication is a database state, not a public path."""
    object_ref = models.CharField(max_length=160, unique=True)
    version = models.CharField(max_length=160)
    context_hash = models.CharField(max_length=64)
    ciphertext_hash = models.CharField(max_length=64)
    size_bytes = models.BigIntegerField()
    state = models.CharField(max_length=16, default='candidate')


class PrivateFileOperation(models.Model):
    """Durable intent before file I/O; result registration shares the owner's transaction."""
    operation_ref = models.CharField(max_length=160, unique=True)
    actor_ref = models.CharField(max_length=160)
    scope_ref = models.CharField(max_length=160)
    request_hash = models.CharField(max_length=64)
    object_uuid = models.UUIDField()
    field_refs = models.JSONField()
    files = models.JSONField(default=dict)
    legacy_sources = models.JSONField(default=dict)
    state = models.CharField(max_length=16, default='preparing')
    result_ref = models.CharField(max_length=160, blank=True)


class PrivateFileShare(models.Model):
    """An expiring reference, never a bearer authorization or public file path."""
    share_id = models.UUIDField(unique=True)
    operation_ref = models.CharField(max_length=160, unique=True)
    document = models.JSONField()
    revoked_at = models.DateTimeField(null=True)


class RecoveryPermission(models.Model):
    """Explicit owner-issued recovery scope; roles and export grants confer no permission."""
    authorization_ref = models.CharField(max_length=160, unique=True)
    actor_ref = models.CharField(max_length=160)
    binding_hash = models.CharField(max_length=64)
    allow_release = models.BooleanField(default=False)
    allow_reconcile = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)


class ExportPlanApproval(models.Model):
    """Two-person target approval; hashes bind the request and object without storing source content."""
    approval_ref = models.CharField(max_length=160, unique=True)
    plan_hash = models.CharField(max_length=64)
    binding_hash = models.CharField(max_length=64)
    context_hash = models.CharField(max_length=64)
    document = models.JSONField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)


class ExportReport(models.Model):
    """Immutable preparation evidence with an optional logical, never network, receipt."""
    execution_id = models.CharField(max_length=160, unique=True)
    idempotency_key = models.CharField(max_length=160, unique=True)
    binding_hash = models.CharField(max_length=64)
    binding_document = models.JSONField(null=True)
    private_object = models.ForeignKey(PrivateObject, to_field='object_ref', on_delete=models.PROTECT, null=True)
    intent_hash = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=16, default='prepared')
    document_hash = models.CharField(max_length=64, blank=True)
    document = models.JSONField(null=True)
    delivery_receipt = models.JSONField(null=True)
    retention_scope = models.CharField(max_length=160, null=True)
    retention_registration = models.JSONField(null=True)
    retention_retirement = models.JSONField(null=True)
    retention_candidate = models.JSONField(null=True)


class RevealRequest(models.Model):
    """Protected reason and owner scope; only server-issued grants may be consumed."""
    request_ref = models.CharField(max_length=160, unique=True, null=True)
    requested_by = models.ForeignKey('users.CTFUser', on_delete=models.PROTECT,
                                     related_name='reveal_requests')
    approved_by = models.ForeignKey('users.CTFUser', on_delete=models.PROTECT, null=True,
                                    related_name='reveal_approvals')
    course_id = models.PositiveBigIntegerField(null=True)
    object_ref = models.CharField(max_length=160)
    object_version = models.CharField(max_length=160)
    fields = models.JSONField()
    purpose_ref = models.CharField(max_length=160)
    reason = models.TextField()
    requested_at = models.DateTimeField()
    decided_by_ref = models.CharField(max_length=160, null=True)
    decided_at = models.DateTimeField(null=True)
    decision_event_ref = models.CharField(max_length=64, null=True)
    grant_id = models.CharField(max_length=160, unique=True, null=True)
    grant_document = models.JSONField(null=True)
    state = models.CharField(max_length=16, default='pending', choices=(
        ('pending', 'pending'), ('approved', 'approved'), ('rejected', 'rejected'),
        ('consumed', 'consumed'), ('revoked', 'revoked'),
    ))
    consumed_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
    retention_scope = models.CharField(max_length=160, null=True)
    retention_registration = models.JSONField(null=True)


class RevealFieldRetention(models.Model):
    """New ciphertext generations only; no original value or plaintext-derived digest."""
    scope_ref = models.CharField(max_length=160)
    object_ref = models.CharField(max_length=160)
    field_ref = models.CharField(max_length=160)
    context_document = models.JSONField()
    generated_at = models.DateTimeField()
    ciphertext_hash = models.CharField(max_length=64)
    registration = models.JSONField()
