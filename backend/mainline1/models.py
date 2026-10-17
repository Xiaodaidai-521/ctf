"""Private parse-task tables. Not registered in production settings yet."""
from django.db import models


class ParseRun(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    domain = models.CharField(max_length=128)
    environment = models.CharField(max_length=16)
    evaluation = models.CharField(max_length=128, default='')
    principal = models.CharField(max_length=128)
    idempotency_key = models.CharField(max_length=128)
    revision = models.PositiveBigIntegerField()
    status = models.CharField(max_length=16, db_index=True)
    state = models.JSONField()  # Private immutable snapshot plus current control state.

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=['domain', 'environment', 'evaluation', 'principal', 'idempotency_key'],
            name='ml1_parse_run_idempotency')]


class ParseAttempt(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    run = models.ForeignKey(ParseRun, on_delete=models.PROTECT)
    number = models.PositiveIntegerField()
    state = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['run', 'number'], name='ml1_parse_attempt_number')]


class ParsedArtifact(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    run = models.OneToOneField(ParseRun, on_delete=models.PROTECT)
    attempt = models.OneToOneField(ParseAttempt, on_delete=models.PROTECT)
    payload = models.JSONField()  # Authorized raw cells: never exposed by admin/HTTP/logs.


class ReviewLedger(models.Model):
    """Bounded internal aggregate, single row serializes all profile-scope changes.

    No production registration. Repository is the only writer; JSON is private.
    A later partitioned schema requires explicit migration and concurrency tests.
    """
    id = models.PositiveSmallIntegerField(primary_key=True, editable=False, default=1)
    state = models.JSONField()

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name='ml1_review_single_ledger')]
