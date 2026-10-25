import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from . import constants


class AssistanceRecord(models.Model):
    """A hint request/show, teacher help or analysis exposure.

    Request and actual display are separate fields.  Only ``shown`` records
    with ``shown_at`` before the final submission count as assistance; an
    analysis view is stored for exposure and review but never counts as a
    hint level.
    """

    record_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='帮助记录 ID')
    event_id = models.CharField(max_length=96, unique=True, verbose_name='事件 ID')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='skill_review_assistance', verbose_name='学生')
    attempt = models.ForeignKey(
        'learning_map.TaskAttempt', null=True, blank=True, on_delete=models.CASCADE,
        related_name='assistance_records', verbose_name='尝试',
    )
    task = models.ForeignKey('learning_map.TaskPackage', on_delete=models.PROTECT, related_name='assistance_records', verbose_name='任务包')
    capability = models.ForeignKey(
        'learning_map.Capability', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='assistance_records', verbose_name='能力',
    )
    kind = models.CharField(max_length=24, choices=constants.ASSISTANCE_KIND_CHOICES, verbose_name='类型')
    level = models.PositiveSmallIntegerField(default=0, verbose_name='提示层级(0-4)')
    source = models.CharField(max_length=16, choices=constants.ASSISTANCE_SOURCE_CHOICES, default=constants.ASSISTANCE_SOURCE_NONE, verbose_name='来源')
    requested_at = models.DateTimeField(null=True, blank=True, verbose_name='请求时间')
    shown_at = models.DateTimeField(null=True, blank=True, verbose_name='实际展示时间')
    shown = models.BooleanField(default=False, verbose_name='是否实际展示')
    content_ref = models.CharField(max_length=255, blank=True, verbose_name='材料引用')
    note = models.TextField(blank=True, verbose_name='说明')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='skill_review_assistance_created', verbose_name='记录人',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '帮助记录'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['attempt', 'kind', 'shown']),
            models.Index(fields=['student', 'task', '-created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(level__gte=0) & models.Q(level__lte=4),
                name='skill_review_assistance_level_0_4',
            ),
        ]

    def __str__(self):
        return f'{self.kind} {self.level} {self.source} shown={self.shown}'


class SubmissionSnapshot(models.Model):
    submission_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='提交 ID')
    client_submission_id = models.CharField(max_length=96, verbose_name='客户端提交标识')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='submissions', verbose_name='尝试')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='skill_review_submissions', verbose_name='学生')
    task = models.ForeignKey('learning_map.TaskPackage', on_delete=models.PROTECT, related_name='submissions', verbose_name='任务包')
    catalog = models.ForeignKey('learning_map.CatalogVersion', on_delete=models.PROTECT, related_name='skill_review_submissions', verbose_name='目录版本')
    task_version = models.CharField(max_length=32, verbose_name='任务版本')
    sequence = models.PositiveIntegerField(verbose_name='提交序号')
    payload = models.JSONField(default=dict, verbose_name='提交内容')
    payload_hash = models.CharField(max_length=64, verbose_name='内容摘要')
    assistance_tracking = models.CharField(
        max_length=16, choices=constants.ASSISTANCE_TRACKING_CHOICES,
        default=constants.ASSISTANCE_TRACKING_COMPLETE, verbose_name='帮助记录完整性',
    )
    assistance_snapshot = models.JSONField(default=dict, blank=True, verbose_name='帮助快照')
    independence = models.CharField(
        max_length=16, choices=constants.INDEPENDENCE_CHOICES,
        default=constants.INDEPENDENCE_UNKNOWN, verbose_name='独立性',
    )
    answer_exposure = models.BooleanField(default=False, verbose_name='同题解析暴露')
    first_effective = models.BooleanField(default=False, verbose_name='首次有效尝试')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='提交时间')

    class Meta:
        verbose_name = '提交快照'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'client_submission_id'],
                name='skill_review_unique_client_submission',
            ),
            models.UniqueConstraint(
                fields=['attempt', 'sequence'],
                name='skill_review_unique_attempt_sequence',
            ),
            models.UniqueConstraint(
                fields=['attempt'],
                condition=models.Q(first_effective=True),
                name='skill_review_one_first_effective_per_attempt',
            ),
        ]
        indexes = [
            models.Index(fields=['student', '-created_at']),
            models.Index(fields=['catalog', 'task', '-created_at']),
        ]

    def __str__(self):
        return f'{self.submission_id} {self.task_id} #{self.sequence}'


class VerificationResult(models.Model):
    result_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='结果 ID')
    submission = models.ForeignKey(SubmissionSnapshot, on_delete=models.CASCADE, related_name='results', verbose_name='提交快照')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='verification_results', verbose_name='尝试')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='skill_review_results', verbose_name='学生')
    task = models.ForeignKey('learning_map.TaskPackage', on_delete=models.PROTECT, related_name='verification_results', verbose_name='任务包')
    catalog = models.ForeignKey('learning_map.CatalogVersion', on_delete=models.PROTECT, related_name='skill_review_results', verbose_name='目录版本')
    version = models.PositiveIntegerField(default=1, verbose_name='结果版本')
    revision = models.PositiveIntegerField(default=1, verbose_name='判定修订号')
    supersedes = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='superseded_by_results', verbose_name='替代的旧结果',
    )
    is_current = models.BooleanField(default=True, verbose_name='是否当前版本')
    program_status = models.CharField(max_length=16, choices=constants.PROGRAM_STATUS_CHOICES, default=constants.PROGRAM_NOT_RUN, verbose_name='程序核验')
    manual_status = models.CharField(max_length=16, choices=constants.MANUAL_STATUS_CHOICES, default=constants.MANUAL_NOT_APPLICABLE, verbose_name='人工评阅')
    overall_status = models.CharField(max_length=24, choices=constants.OVERALL_STATUS_CHOICES, default=constants.OVERALL_PENDING, verbose_name='综合结论')
    independence = models.CharField(max_length=16, choices=constants.INDEPENDENCE_CHOICES, verbose_name='独立性')
    assistance_snapshot = models.JSONField(default=dict, blank=True, verbose_name='帮助快照')
    item_results = models.JSONField(default=list, verbose_name='分项结果')
    program_result = models.JSONField(default=dict, blank=True, verbose_name='程序核验明细')
    manual_result = models.JSONField(default=dict, blank=True, verbose_name='人工评阅明细')
    verifier_version = models.CharField(max_length=64, blank=True, verbose_name='验证器版本')
    rubric_version = models.CharField(max_length=64, blank=True, verbose_name='量表版本')
    verification_error = models.CharField(max_length=96, blank=True, verbose_name='核验异常原因')
    module1_fact_ids = models.JSONField(default=dict, blank=True, verbose_name='模块一事实 ID')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '核验结果'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['submission', 'version'], name='skill_review_unique_result_version'),
            models.UniqueConstraint(
                fields=['submission'],
                condition=models.Q(is_current=True),
                name='skill_review_one_current_result',
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'task', '-created_at']),
            models.Index(fields=['overall_status', '-created_at']),
        ]

    def __str__(self):
        return f'{self.result_id} v{self.version} {self.overall_status}'


class ManualReviewTask(models.Model):
    review_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='人工待办 ID')
    result = models.OneToOneField(VerificationResult, on_delete=models.CASCADE, related_name='manual_task', verbose_name='核验结果')
    submission = models.ForeignKey(SubmissionSnapshot, on_delete=models.CASCADE, related_name='manual_tasks', verbose_name='提交快照')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='manual_tasks', verbose_name='尝试')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='skill_review_manual_tasks', verbose_name='学生')
    task = models.ForeignKey('learning_map.TaskPackage', on_delete=models.PROTECT, related_name='manual_tasks', verbose_name='任务包')
    catalog = models.ForeignKey('learning_map.CatalogVersion', on_delete=models.PROTECT, related_name='manual_tasks', verbose_name='目录版本')
    status = models.CharField(max_length=16, choices=constants.MANUAL_TASK_STATUS_CHOICES, default=constants.MANUAL_TASK_PENDING, verbose_name='状态')
    rubric = models.JSONField(default=list, verbose_name='量表快照')
    rubric_version = models.CharField(max_length=64, default=constants.RUBRIC_VERSION, verbose_name='量表版本')
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='skill_review_manual_claimed', verbose_name='认领教师',
    )
    claimed_at = models.DateTimeField(null=True, blank=True, verbose_name='认领时间')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='skill_review_manual_reviewed', verbose_name='评阅教师',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='评阅时间')
    scores = models.JSONField(default=dict, blank=True, verbose_name='分项得分')
    total_score = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='总分')
    decision = models.CharField(
        max_length=16, blank=True,
        choices=[('pass', '通过'), ('fail', '未通过')], verbose_name='评阅结论',
    )
    remarks = models.TextField(blank=True, verbose_name='评阅说明')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '人工评阅待办'
        verbose_name_plural = verbose_name
        ordering = ['created_at']
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self):
        return f'{self.task_id} {self.status}'


class SubmissionErrorCause(models.Model):
    submission = models.ForeignKey(SubmissionSnapshot, on_delete=models.CASCADE, related_name='error_causes', verbose_name='提交快照')
    cause = models.CharField(max_length=24, choices=constants.ERROR_CAUSE_CHOICES, verbose_name='错因')
    status = models.CharField(max_length=16, choices=constants.CAUSE_STATUS_CHOICES, default=constants.CAUSE_SUGGESTED, verbose_name='确认状态')
    source = models.CharField(max_length=16, choices=constants.CAUSE_SOURCE_CHOICES, default=constants.CAUSE_SOURCE_SYSTEM, verbose_name='来源')
    note = models.TextField(blank=True, verbose_name='说明')
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='skill_review_causes_confirmed', verbose_name='确认人',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '错因确认'
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(fields=['submission', 'cause'], name='skill_review_unique_error_cause'),
        ]

    def __str__(self):
        return f'{self.submission_id} {self.cause} {self.status}'


class ReviewCard(models.Model):
    card_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='复盘卡 ID')
    submission = models.OneToOneField(SubmissionSnapshot, on_delete=models.CASCADE, related_name='review_card', verbose_name='提交快照')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='skill_review_cards', verbose_name='学生')
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='review_cards', verbose_name='尝试')
    task = models.ForeignKey('learning_map.TaskPackage', on_delete=models.PROTECT, related_name='review_cards', verbose_name='任务包')
    catalog = models.ForeignKey('learning_map.CatalogVersion', on_delete=models.PROTECT, related_name='review_cards', verbose_name='目录版本')
    status = models.CharField(max_length=16, choices=constants.REVIEW_CARD_STATUS_CHOICES, default=constants.REVIEW_CARD_DRAFT, verbose_name='状态')
    original_task_summary = models.TextField(blank=True, verbose_name='原任务与知识点')
    error_evidence = models.TextField(blank=True, verbose_name='错误证据')
    judgment_at_time = models.TextField(blank=True, verbose_name='当时判断')
    correct_basis = models.TextField(blank=True, verbose_name='正确依据或方法')
    next_verification = models.TextField(blank=True, verbose_name='下一次如何验证')
    student_reflection = models.TextField(blank=True, verbose_name='学生反思')
    teacher_confirmation = models.TextField(blank=True, verbose_name='教师确认')
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='skill_review_cards_confirmed', verbose_name='确认教师',
    )
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name='确认时间')
    assistance_level = models.PositiveSmallIntegerField(default=0, verbose_name='当时帮助层级')
    assistance_source = models.CharField(max_length=16, choices=constants.ASSISTANCE_SOURCE_CHOICES, default=constants.ASSISTANCE_SOURCE_NONE, verbose_name='帮助来源')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '复盘卡'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.card_id} {self.status}'


class RetestAssignment(models.Model):
    assignment_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='复测安排 ID')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='skill_review_retests', verbose_name='学生')
    catalog = models.ForeignKey('learning_map.CatalogVersion', on_delete=models.PROTECT, related_name='skill_review_retests', verbose_name='目录版本')
    capability = models.ForeignKey('learning_map.Capability', null=True, blank=True, on_delete=models.SET_NULL, related_name='skill_review_retests', verbose_name='知识点/能力')
    capability_ids = models.JSONField(default=list, verbose_name='能力 ID 快照')
    original_attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT, related_name='retest_assignments', verbose_name='原尝试')
    original_submission = models.OneToOneField(SubmissionSnapshot, on_delete=models.PROTECT, related_name='retest_assignment', verbose_name='原提交')
    pool_snapshot = models.JSONField(default=dict, verbose_name='题池快照')
    selected_task = models.ForeignKey(
        'learning_map.TaskPackage', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='retest_assignments', verbose_name='复测任务',
    )
    selection_reason = models.CharField(max_length=64, blank=True, verbose_name='选中原因')
    rule_version = models.CharField(max_length=64, default=constants.RULE_VERSION, verbose_name='规则版本')
    status = models.CharField(max_length=24, choices=constants.RETEST_STATUS_CHOICES, default=constants.RETEST_PENDING_ITEM, verbose_name='状态')
    scheduled_at = models.DateTimeField(null=True, blank=True, verbose_name='安排时间')
    due_at = models.DateTimeField(null=True, blank=True, verbose_name='到期时间')
    grace_until = models.DateTimeField(null=True, blank=True, verbose_name='宽限截止')
    started_attempt = models.ForeignKey(
        'learning_map.TaskAttempt', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='retest_started_for', verbose_name='复测尝试',
    )
    completed_submission = models.ForeignKey(
        SubmissionSnapshot, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='completed_retests', verbose_name='复测提交',
    )
    adjustment_note = models.TextField(blank=True, verbose_name='改期或调整说明')
    outcome = models.CharField(max_length=24, choices=constants.RETEST_OUTCOME_CHOICES, blank=True, verbose_name='复测结果')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '复测安排'
        verbose_name_plural = verbose_name
        ordering = ['due_at', 'created_at']
        indexes = [models.Index(fields=['status', 'due_at'])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[
                    constants.RETEST_PENDING_ITEM, constants.RETEST_SCHEDULED,
                    constants.RETEST_DUE, constants.RETEST_IN_PROGRESS,
                    constants.RETEST_COMPLETED, constants.RETEST_MISSED,
                    constants.RETEST_WAIVED,
                ]),
                name='skill_review_valid_retest_status',
            ),
        ]

    def __str__(self):
        return f'{self.assignment_id} {self.status}'


class TeacherSamplingBatch(models.Model):
    batch_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='抽查批次 ID')
    title = models.CharField(max_length=200, verbose_name='批次名称')
    catalog = models.ForeignKey('learning_map.CatalogVersion', on_delete=models.PROTECT, related_name='sampling_batches', verbose_name='目录版本')
    task = models.ForeignKey('learning_map.TaskPackage', null=True, blank=True, on_delete=models.SET_NULL, related_name='sampling_batches', verbose_name='任务')
    capability = models.ForeignKey('learning_map.Capability', null=True, blank=True, on_delete=models.SET_NULL, related_name='sampling_batches', verbose_name='能力')
    scope = models.JSONField(default=dict, verbose_name='范围快照')
    window_start = models.DateTimeField(verbose_name='时间窗开始')
    window_end = models.DateTimeField(verbose_name='时间窗结束')
    sample_size = models.PositiveIntegerField(default=0, verbose_name='随机样本数')
    high_risk_size = models.PositiveIntegerField(default=0, verbose_name='高风险样本数')
    random_seed = models.IntegerField(default=0, verbose_name='随机种子')
    basis = models.TextField(verbose_name='抽样依据')
    deadline = models.DateTimeField(verbose_name='完成期限')
    status = models.CharField(max_length=16, choices=constants.SAMPLING_STATUS_CHOICES, default=constants.SAMPLING_OPEN, verbose_name='状态')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='skill_review_sampling_created', verbose_name='创建人',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '教师抽查批次'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class TeacherSamplingItem(models.Model):
    item_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='抽查项 ID')
    batch = models.ForeignKey(TeacherSamplingBatch, on_delete=models.CASCADE, related_name='items', verbose_name='批次')
    submission = models.ForeignKey(SubmissionSnapshot, on_delete=models.CASCADE, related_name='sampling_items', verbose_name='提交快照')
    result = models.ForeignKey(VerificationResult, null=True, blank=True, on_delete=models.SET_NULL, related_name='sampling_items', verbose_name='核验结果')
    selection_reason = models.CharField(max_length=32, choices=constants.SAMPLING_SELECTION_CHOICES, verbose_name='入选原因')
    risk_reasons = models.JSONField(default=list, blank=True, verbose_name='高风险原因')
    status = models.CharField(max_length=24, choices=constants.SAMPLING_ITEM_STATUS_CHOICES, default=constants.SAMPLING_ITEM_PENDING, verbose_name='状态')
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='skill_review_sampling_claimed', verbose_name='认领教师',
    )
    claimed_at = models.DateTimeField(null=True, blank=True, verbose_name='认领时间')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='skill_review_sampling_reviewed', verbose_name='复核教师',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='复核时间')
    findings = models.JSONField(default=dict, blank=True, verbose_name='复核记录')
    notes = models.TextField(blank=True, verbose_name='说明')
    correction = models.ForeignKey('ResultCorrection', null=True, blank=True, on_delete=models.SET_NULL, related_name='sampling_items', verbose_name='更正')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '教师抽查项'
        verbose_name_plural = verbose_name
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['batch', 'submission'], name='skill_review_unique_sampling_item'),
        ]

    def __str__(self):
        return f'{self.item_id} {self.selection_reason}'


class ScoreDispute(models.Model):
    dispute_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='争议 ID')
    client_dispute_id = models.CharField(max_length=96, verbose_name='客户端争议标识')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='skill_review_disputes', verbose_name='学生')
    submission = models.ForeignKey(SubmissionSnapshot, on_delete=models.CASCADE, related_name='disputes', verbose_name='提交快照')
    result = models.ForeignKey(VerificationResult, null=True, blank=True, on_delete=models.SET_NULL, related_name='disputes', verbose_name='核验结果')
    reason = models.TextField(verbose_name='争议内容')
    status = models.CharField(max_length=16, choices=constants.DISPUTE_STATUS_CHOICES, default=constants.DISPUTE_SUBMITTED, verbose_name='状态')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='skill_review_disputes_assigned', verbose_name='处理教师',
    )
    resolution = models.TextField(blank=True, verbose_name='处理结论')
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='skill_review_disputes_resolved', verbose_name='处理人',
    )
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='处理时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '评分争议'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['student', 'client_dispute_id'], name='skill_review_unique_client_dispute'),
        ]

    def __str__(self):
        return f'{self.dispute_id} {self.status}'


class ResultCorrection(models.Model):
    correction_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='更正 ID')
    submission = models.ForeignKey(SubmissionSnapshot, on_delete=models.CASCADE, related_name='corrections', verbose_name='提交快照')
    original_result = models.ForeignKey(VerificationResult, on_delete=models.PROTECT, related_name='corrections_from', verbose_name='原结果')
    corrected_result = models.ForeignKey(VerificationResult, on_delete=models.PROTECT, related_name='corrections_to', verbose_name='更正结果')
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='skill_review_corrections', verbose_name='复核人',
    )
    source = models.CharField(max_length=24, choices=constants.CORRECTION_SOURCE_CHOICES, verbose_name='来源')
    reason = models.TextField(verbose_name='更正理由')
    before = models.JSONField(default=dict, verbose_name='原判定')
    after = models.JSONField(default=dict, verbose_name='更正后判定')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='更正时间')

    class Meta:
        verbose_name = '结果更正'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.correction_id} {self.source}'


class DownstreamNotice(models.Model):
    notice_key = models.CharField(max_length=160, unique=True, verbose_name='通知键')
    result = models.ForeignKey(VerificationResult, on_delete=models.CASCADE, related_name='notices', verbose_name='核验结果')
    correction = models.ForeignKey(ResultCorrection, null=True, blank=True, on_delete=models.CASCADE, related_name='notices', verbose_name='更正')
    target = models.CharField(max_length=16, choices=constants.NOTICE_TARGET_CHOICES, verbose_name='目标模块')
    status = models.CharField(max_length=16, choices=constants.NOTICE_STATUS_CHOICES, default=constants.NOTICE_PENDING, verbose_name='状态')
    target_connected = models.BooleanField(default=False, verbose_name='目标已接通')
    payload = models.JSONField(default=dict, verbose_name='通知内容')
    attempts = models.PositiveIntegerField(default=0, verbose_name='尝试次数')
    last_error = models.CharField(max_length=255, blank=True, verbose_name='最后错误')
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='发送时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '下游通知'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [models.Index(fields=['target', 'status'])]

    def __str__(self):
        return f'{self.target} {self.status}'
