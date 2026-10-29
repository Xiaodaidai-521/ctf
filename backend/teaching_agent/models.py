import uuid

from django.conf import settings
from django.db import models


class TeachingRun(models.Model):
    MODE_DATA_SECURITY = 'data_security'
    MODE_NETWORK_SECURITY = 'network_security'
    MODE_REVIEW = 'review'
    MODE_CHOICES = [
        (MODE_DATA_SECURITY, '数据安全导师'),
        (MODE_NETWORK_SECURITY, '网络安全实训导师'),
        (MODE_REVIEW, '验收复盘助手'),
    ]

    STATE_READY = 'ready'
    STATE_WAITING_AI = 'waiting_ai'
    STATE_SHOWING_HELP = 'showing_help'
    STATE_PAUSED = 'paused'
    STATE_WAITING_TEACHER = 'waiting_teacher'
    STATE_DEGRADED = 'degraded'
    STATE_ENDED = 'ended'
    STATE_CHOICES = [
        (STATE_READY, '就绪'),
        (STATE_WAITING_AI, '等待 AI'),
        (STATE_SHOWING_HELP, '展示帮助'),
        (STATE_PAUSED, '已暂停'),
        (STATE_WAITING_TEACHER, '等待教师'),
        (STATE_DEGRADED, '已降级'),
        (STATE_ENDED, '已结束'),
    ]

    run_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teaching_runs')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='teaching_runs')
    mode = models.CharField(max_length=24, choices=MODE_CHOICES)
    state = models.CharField(max_length=24, choices=STATE_CHOICES, default=STATE_READY)
    state_version = models.PositiveIntegerField(default=1)
    context_version = models.PositiveIntegerField(default=1)
    permission_version = models.PositiveIntegerField(default=1)
    hint_level = models.PositiveSmallIntegerField(default=0)
    task_version = models.CharField(max_length=32)
    catalog_version = models.CharField(max_length=32)
    context_snapshot = models.JSONField(default=dict, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'state']),
            models.Index(fields=['attempt', '-created_at']),
        ]


class HintCard(models.Model):
    task = models.ForeignKey('learning_map.TaskPackage', on_delete=models.CASCADE, related_name='teaching_hint_cards')
    level = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    content = models.TextField()
    material_ref = models.CharField(max_length=255, blank=True)
    version = models.CharField(max_length=32, default='1.0.0')
    unlock_rule = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['task', 'level']
        constraints = [
            models.UniqueConstraint(fields=['task', 'level', 'version'], name='teaching_unique_hint_card_version'),
            models.CheckConstraint(condition=models.Q(level__gte=1) & models.Q(level__lte=4), name='teaching_hint_level_1_4'),
        ]


class TeacherTicket(models.Model):
    STATUS_OPEN = 'open'
    STATUS_CLAIMED = 'claimed'
    STATUS_HELPED = 'helped'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_OPEN, '待处理'),
        (STATUS_CLAIMED, '已认领'),
        (STATUS_HELPED, '已提供帮助'),
        (STATUS_CLOSED, '已关闭'),
    ]

    ticket_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    run = models.ForeignKey(TeachingRun, on_delete=models.CASCADE, related_name='tickets')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='teaching_tickets')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teaching_tickets')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN)
    question_summary = models.TextField(blank=True)
    claimed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='claimed_teaching_tickets')
    claimed_at = models.DateTimeField(null=True, blank=True)
    helped_at = models.DateTimeField(null=True, blank=True)
    actual_help_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class HintDelivery(models.Model):
    request_id = models.CharField(max_length=64, unique=True)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teaching_hint_deliveries')
    run = models.ForeignKey(TeachingRun, on_delete=models.CASCADE, related_name='hint_deliveries')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='teaching_hint_deliveries')
    card = models.ForeignKey(HintCard, on_delete=models.PROTECT, related_name='deliveries')
    assistance_record = models.OneToOneField('skill_review.AssistanceRecord', on_delete=models.PROTECT, related_name='teaching_delivery')
    source = models.CharField(max_length=16, default='card')
    payload_hash = models.CharField(max_length=64)
    permission_version = models.PositiveIntegerField()
    displayed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class StudentAnalysis(models.Model):
    task = models.ForeignKey('learning_map.TaskPackage', on_delete=models.CASCADE, related_name='student_analyses')
    version = models.CharField(max_length=32, default='1.0.0')
    title = models.CharField(max_length=200)
    content = models.TextField()
    content_ref = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['task', 'version'], name='teaching_unique_student_analysis_version'),
        ]


class TutorRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_DEGRADED = 'degraded'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, '处理中'),
        (STATUS_SUCCEEDED, '成功'),
        (STATUS_DEGRADED, '已降级'),
        (STATUS_FAILED, '失败'),
    ]

    request_id = models.CharField(max_length=64, unique=True)
    idempotency_key = models.CharField(max_length=64)
    payload_hash = models.CharField(max_length=64)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teaching_tutor_requests')
    run = models.ForeignKey(TeachingRun, on_delete=models.CASCADE, related_name='requests')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='teaching_tutor_requests')
    hint_level = models.PositiveSmallIntegerField(default=1)
    context_version = models.PositiveIntegerField()
    permission_version = models.PositiveIntegerField()
    material_hash = models.CharField(max_length=64, default='')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    response = models.JSONField(default=dict, blank=True)
    fallback_card = models.ForeignKey(HintCard, null=True, blank=True, on_delete=models.SET_NULL, related_name='fallback_requests')
    late_response_discarded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'idempotency_key'], name='teaching_unique_student_request_key'),
        ]


class TutorResponseCache(models.Model):
    cache_key = models.CharField(max_length=64, unique=True)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teaching_response_cache_entries')
    run = models.ForeignKey(TeachingRun, on_delete=models.CASCADE, related_name='response_cache_entries')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.CASCADE, related_name='teaching_response_cache_entries')
    subject = models.CharField(max_length=128)
    hint_level = models.PositiveSmallIntegerField()
    context_version = models.PositiveIntegerField()
    permission_version = models.PositiveIntegerField()
    material_hash = models.CharField(max_length=64)
    response = models.JSONField(default=dict)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['student', 'subject', 'permission_version'])]


class ModelCallRecord(models.Model):
    request = models.ForeignKey(TutorRequest, on_delete=models.CASCADE, related_name='model_calls')
    call_id = models.CharField(max_length=64, unique=True)
    provider = models.CharField(max_length=64, blank=True)
    model = models.CharField(max_length=128, blank=True)
    template_version = models.CharField(max_length=64, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=32)
    error_category = models.CharField(max_length=32, blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    cancellation_status = models.CharField(max_length=32, blank=True)
    cost_amount = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    cost_currency = models.CharField(max_length=8, blank=True)
    cost_basis = models.CharField(max_length=64, default='unknown')
    provider_request_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ResumeReceipt(models.Model):
    request_id = models.CharField(max_length=64, unique=True)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teaching_resume_receipts')
    run = models.ForeignKey(TeachingRun, on_delete=models.CASCADE, related_name='resume_receipts')
    expected_state_version = models.PositiveIntegerField()
    payload_hash = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ProviderCircuit(models.Model):
    provider = models.CharField(max_length=64, unique=True)
    state = models.CharField(max_length=16, default='closed')
    failure_count = models.PositiveIntegerField(default=0)
    config_version = models.CharField(max_length=64, default='unapproved-default')
    opened_at = models.DateTimeField(null=True, blank=True)
    next_probe_at = models.DateTimeField(null=True, blank=True)
    last_probe_status = models.CharField(max_length=32, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class PracticeAction(models.Model):
    STATUS_REGISTERED = 'registered'
    STATUS_UNAVAILABLE = 'unavailable'
    STATUS_NOT_APPLICABLE = 'not_applicable'
    STATUS_CHOICES = [
        (STATUS_REGISTERED, '已登记'),
        (STATUS_UNAVAILABLE, '依赖未接入'),
        (STATUS_NOT_APPLICABLE, '不适用'),
    ]

    action_id = models.CharField(max_length=64, unique=True)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teaching_practice_actions')
    run = models.ForeignKey(TeachingRun, on_delete=models.CASCADE, related_name='practice_actions')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='teaching_practice_actions')
    action_type = models.CharField(max_length=32)
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    dependency = models.CharField(max_length=32, blank=True)
    evidence_ref = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
