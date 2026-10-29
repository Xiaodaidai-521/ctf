import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ChallengeMapping(models.Model):
    """Teaching metadata stays in module one's versioned task packages."""

    task = models.OneToOneField('learning_map.TaskPackage', on_delete=models.PROTECT)
    repair_task = models.ForeignKey(
        'learning_map.TaskPackage', on_delete=models.PROTECT, related_name='repair_mappings',
    )
    challenge_key = models.CharField(max_length=80, default='directoryListingChallenge')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_ref = models.CharField(max_length=255, blank=True)
    review_hash = models.CharField(max_length=64, blank=True)
    paused = models.BooleanField(default=False)


class EnvironmentApproval(models.Model):
    """Operator attestation, not a substitute for external isolation evidence."""

    container = models.OneToOneField('challenges.ChallengeContainer', on_delete=models.PROTECT)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    evidence_ref = models.CharField(max_length=255)
    checks = models.JSONField(default=dict)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)
    revoked = models.BooleanField(default=False)


class LabAssignment(models.Model):
    assignment_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    mapping = models.ForeignKey(ChallengeMapping, on_delete=models.PROTECT)
    attempt = models.OneToOneField('learning_map.TaskAttempt', on_delete=models.PROTECT)
    container = models.OneToOneField('challenges.ChallengeContainer', on_delete=models.PROTECT)
    task_snapshot = models.JSONField(default=dict)
    scope = models.JSONField(default=dict)
    policy = models.JSONField(default=dict)
    accepted_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    state = models.CharField(max_length=24, default='allocated', choices=[
        ('allocated', '已分配'), ('active', '练习中'), ('paused', '已暂停'),
        ('isolated', '平台隔离'), ('reset', '已重置授权'), ('expired', '到期回收授权'),
    ])
    physical_cleanup = models.CharField(max_length=24, default='not_requested')
    baseline_observed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class ServerEvidence(models.Model):
    evidence_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    assignment = models.ForeignKey(LabAssignment, on_delete=models.PROTECT, related_name='evidence')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT)
    key = models.CharField(max_length=64, unique=True)
    request_hash = models.CharField(max_length=64)
    source = models.JSONField(default=dict)
    observation = models.JSONField(default=dict)
    content_hash = models.CharField(max_length=64)
    verifier_version = models.CharField(max_length=64)
    status = models.CharField(max_length=24, choices=[('passed', '通过'), ('failed', '未通过'), ('error', '核验故障')])
    error = models.CharField(max_length=96, blank=True)
    observed_at = models.DateTimeField(default=timezone.now)
    result = models.OneToOneField('skill_review.VerificationResult', null=True, on_delete=models.PROTECT)


class RepairClaim(models.Model):
    claim_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    assignment = models.ForeignKey(LabAssignment, on_delete=models.PROTECT, related_name='repair_claims')
    retest = models.OneToOneField('skill_review.RetestAssignment', on_delete=models.PROTECT)
    attempt = models.OneToOneField('learning_map.TaskAttempt', on_delete=models.PROTECT)
    key = models.CharField(max_length=64, unique=True)
    payload = models.JSONField(default=dict)
    payload_hash = models.CharField(max_length=64)
    evidence = models.OneToOneField(ServerEvidence, null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    @property
    def completed(self):
        return bool(self.evidence_id and self.evidence.result_id
                    and self.evidence.result.overall_status == 'passed')
