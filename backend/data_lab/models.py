"""Teaching evidence only. No export authorization, quota or grade tables."""
import uuid
from django.conf import settings
from django.db import models


class CasePackage(models.Model):
    task = models.OneToOneField('learning_map.TaskPackage', on_delete=models.PROTECT, related_name='data_lab_case')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='data_lab_owned_cases')
    teachers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='data_lab_cases')
    material_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default='draft')
    paused = models.BooleanField(default=False)
    withdrawn = models.BooleanField(default=False)
    author_review = models.JSONField(default=dict)
    second_review = models.JSONField(default=dict)
    release_checks = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class LabAttempt(models.Model):
    attempt = models.OneToOneField('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='data_lab_state')
    case = models.ForeignKey(CasePackage, on_delete=models.PROTECT)
    basis = models.JSONField(default=dict)
    basis_digest = models.CharField(max_length=64, blank=True)
    active_scan = models.ForeignKey('Scan', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    revision = models.PositiveIntegerField(default=0)
    tracking = models.CharField(max_length=16, default='complete')


class Scan(models.Model):
    scan_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    lab = models.ForeignKey(LabAttempt, on_delete=models.PROTECT, related_name='scans')
    idempotency_key = models.CharField(max_length=64)
    request_digest = models.CharField(max_length=64)
    asset_id = models.UUIDField(default=uuid.uuid4, editable=False)
    asset_version_id = models.UUIDField(default=uuid.uuid4, editable=False)
    asset_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default='running')
    failure_code = models.CharField(max_length=64, blank=True)
    parsed = models.JSONField(default=dict)
    original = models.JSONField(default=dict)
    current_profile_id = models.UUIDField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lab', 'idempotency_key'], name='dl_scan_idempotency')]


class ReviewLedger(models.Model):
    scan = models.OneToOneField(Scan, on_delete=models.PROTECT, related_name='ledger')
    state = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=0)


class ProfileIndex(models.Model):
    profile_id = models.UUIDField(unique=True)
    scan = models.ForeignKey(Scan, on_delete=models.PROTECT, related_name='profiles')


class Replay(models.Model):
    replay_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    lab = models.ForeignKey(LabAttempt, on_delete=models.PROTECT, related_name='replays')
    scan = models.ForeignKey(Scan, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=64)
    request_digest = models.CharField(max_length=64)
    variant = models.CharField(max_length=8)
    profile_id = models.UUIDField()
    judgment = models.JSONField(default=dict)
    frozen = models.JSONField(default=dict)
    content_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lab', 'idempotency_key'], name='dl_replay_idempotency')]


class EvidenceSubmission(models.Model):
    submission_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    lab = models.ForeignKey(LabAttempt, on_delete=models.PROTECT, related_name='submissions')
    idempotency_key = models.CharField(max_length=64)
    request_digest = models.CharField(max_length=64)
    snapshot = models.JSONField(default=dict)
    content_digest = models.CharField(max_length=64)
    module6 = models.OneToOneField('skill_review.SubmissionSnapshot', null=True, blank=True, on_delete=models.PROTECT, related_name='data_lab_evidence')
    status = models.CharField(max_length=24, default='pending')
    failure_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lab', 'idempotency_key'], name='dl_submission_idempotency')]


class HelpRequest(models.Model):
    request_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    lab = models.ForeignKey(LabAttempt, on_delete=models.PROTECT, related_name='help_requests')
    idempotency_key = models.CharField(max_length=64)
    request_digest = models.CharField(max_length=64)
    record = models.OneToOneField('skill_review.AssistanceRecord', on_delete=models.PROTECT)
    material_version = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lab', 'idempotency_key'], name='dl_help_idempotency')]
