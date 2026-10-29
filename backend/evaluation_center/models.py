import uuid

from django.conf import settings
from django.db import models


class NonFormalAccount(models.Model):
    """Explicit provenance for test/demo accounts; unmarked students are formal."""

    student = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name='evaluation_data_source')
    source = models.CharField(max_length=16, choices=[('demo', '演示'), ('offline', '离线评测')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(source__in=['demo', 'offline']),
                                               name='m8_nonformal_source')]


class TeacherTodo(models.Model):
    todo_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source_key = models.CharField(max_length=160, unique=True)
    source_snapshot = models.JSONField(default=dict)
    kind = models.CharField(max_length=24, choices=[
        ('help', '主动求助'), ('manual_review', '开放题必评'),
        ('sampling', '常规抽查'), ('dispute', '争议复核'), ('evidence', '证据异常'),
    ])
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='evaluation_todos')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='evaluation_todos')
    proposal = models.ForeignKey('learning_analytics.LearningAdjustmentProposal', null=True, blank=True, on_delete=models.PROTECT)
    original_result = models.ForeignKey('skill_review.VerificationResult', null=True, blank=True, on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='evaluation_owned_todos')
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=32, default='unclaimed')
    summary = models.CharField(max_length=1000, blank=True)
    retest = models.ForeignKey('skill_review.RetestAssignment', null=True, blank=True, on_delete=models.PROTECT)
    proof = models.JSONField(default=dict)
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TodoAction(models.Model):
    todo = models.ForeignKey(TeacherTodo, on_delete=models.CASCADE, related_name='actions')
    revision = models.PositiveIntegerField()
    action = models.CharField(max_length=32)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    old_owner_id = models.PositiveBigIntegerField(null=True)
    new_owner_id = models.PositiveBigIntegerField(null=True)
    summary = models.CharField(max_length=1000, blank=True)
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['todo', 'revision'], name='m8_todo_action_revision')]


class ProjectionReceipt(models.Model):
    notice_key = models.CharField(max_length=160, unique=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class EvaluationRun(models.Model):
    """Offline-only execution, with a content-addressed, server-owned manifest."""

    run_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    candidate = models.ForeignKey('feedback_center.FeedbackCandidate', on_delete=models.PROTECT,
                                  related_name='evaluation_runs')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name='offline_evaluation_runs')
    frozen = models.JSONField()
    manifest_digest = models.CharField(max_length=64)
    state = models.CharField(max_length=24, default='created')
    stop_reason = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        permissions = [('manage_evaluation', 'Can manage isolated offline evaluations')]


class EvaluationCaseResult(models.Model):
    run = models.ForeignKey(EvaluationRun, on_delete=models.PROTECT, related_name='case_results')
    case_id = models.CharField(max_length=100)
    ordinal = models.PositiveIntegerField()
    payload = models.JSONField()
    result_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ordinal']
        constraints = [
            models.UniqueConstraint(fields=['run', 'case_id'], name='m8_eval_case_once'),
            models.UniqueConstraint(fields=['run', 'ordinal'], name='m8_eval_ordinal_once'),
        ]


class EvaluationReport(models.Model):
    report_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    run = models.OneToOneField(EvaluationRun, on_delete=models.PROTECT, related_name='report')
    report_version = models.CharField(max_length=32, default='m8-report/1')
    payload = models.JSONField()
    report_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
