"""Persistence for module 7 phase 1.

Design rules enforced here:

* A feedback ticket has its own business state, but it never stores a second
  copy of a learning fact.  It references module 1 task/attempt/catalog rows and
  module 6 ``VerificationFact`` / ``LearningEvent`` rows.
* Original submissions, review conclusions, actions and evidence are
  append-only.  A correction adds a new review row; it never overwrites the
  original.
* Missing links are allowed and visible.  They make a ticket ineligible as a
  candidate basis, but they do not fabricate a fact.
* No model in this app can change a student score, a verification fact or a
  production policy.
"""

import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from . import constants


def feedback_attachment_path(instance, filename):
    """Store evidence under a ticket-scoped, unpredictable path.

    The original filename is never used as a path.  Download is only available
    through the permission-checked API endpoint, not through a public media URL.
    """

    safe_name = os.path.basename(filename or 'attachment')
    return f'feedback_evidence/{instance.ticket.feedback_id}/{uuid.uuid4().hex}_{safe_name}'


class FeedbackTicket(models.Model):
    feedback_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='反馈 ID')
    client_request_id = models.CharField(max_length=128, verbose_name='客户端提交标识')
    request_fingerprint = models.CharField(max_length=64, verbose_name='提交内容摘要')

    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='feedback_submitted', verbose_name='提交者',
    )
    submitter_role = models.CharField(max_length=16, verbose_name='提交者角色快照')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='feedback_received', verbose_name='反馈所属学生',
    )

    catalog = models.ForeignKey(
        'learning_map.CatalogVersion', null=True, blank=True, on_delete=models.PROTECT,
        related_name='feedback_tickets', verbose_name='目录版本',
    )
    task = models.ForeignKey(
        'learning_map.TaskPackage', null=True, blank=True, on_delete=models.PROTECT,
        related_name='feedback_tickets', verbose_name='任务包',
    )
    task_version = models.CharField(max_length=32, blank=True, verbose_name='任务版本快照')
    attempt = models.ForeignKey(
        'learning_map.TaskAttempt', null=True, blank=True, on_delete=models.PROTECT,
        related_name='feedback_tickets', verbose_name='任务尝试',
    )
    attempt_ref = models.CharField(max_length=128, blank=True, verbose_name='外部/未映射尝试引用')
    capability = models.ForeignKey(
        'learning_map.Capability', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_tickets', verbose_name='能力',
    )
    knowledge_point = models.ForeignKey(
        'learning_map.KnowledgePoint', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_tickets', verbose_name='知识点',
    )

    category = models.CharField(max_length=16, choices=constants.CATEGORY_CHOICES, verbose_name='反馈类别')
    issue_type = models.CharField(max_length=48, verbose_name='具体问题类型')
    dispute = models.TextField(verbose_name='具体争议')
    expected_result = models.TextField(blank=True, verbose_name='期望结果')
    reason = models.TextField(blank=True, verbose_name='理由')

    original_decision_ref = models.CharField(max_length=255, blank=True, verbose_name='原始判定引用')
    original_decision_version = models.CharField(max_length=64, blank=True, verbose_name='原始判定版本')
    original_decision_snapshot = models.JSONField(default=dict, blank=True, verbose_name='原始判定摘要')
    context_snapshot = models.JSONField(default=dict, blank=True, verbose_name='提交时上下文摘要')

    involves_actual_execution = models.BooleanField(default=False, verbose_name='涉及实际执行')
    technical_issue = models.BooleanField(default=False, verbose_name='技术故障')

    status = models.CharField(
        max_length=24, choices=constants.STATUS_CHOICES,
        default=constants.STATUS_SUBMITTED, verbose_name='工单状态',
    )
    version = models.PositiveIntegerField(default=1, verbose_name='工单版本')
    dedup_key = models.CharField(max_length=64, db_index=True, verbose_name='同尝试去重键')
    duplicate_of = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='duplicates', verbose_name='主记录',
    )
    missing_evidence = models.JSONField(default=list, blank=True, verbose_name='缺失证据槽')

    impact_level = models.CharField(
        max_length=16, choices=constants.IMPACT_CHOICES,
        default=constants.IMPACT_UNKNOWN, verbose_name='影响',
    )
    novelty = models.CharField(
        max_length=16, choices=constants.NOVELTY_CHOICES,
        default=constants.NOVELTY_UNKNOWN, verbose_name='新颖性',
    )
    conflict_flag = models.BooleanField(default=False, verbose_name='证据冲突')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_owned', verbose_name='责任人',
    )
    owner_role = models.CharField(
        max_length=24, choices=constants.OWNER_ROLE_CHOICES,
        default=constants.OWNER_TEACHER, verbose_name='责任角色',
    )
    assigned_at = models.DateTimeField(null=True, blank=True, verbose_name='认领/分配时间')
    due_at = models.DateTimeField(null=True, blank=True, verbose_name='补证/处理期限')

    handling_destination = models.CharField(
        max_length=32, choices=constants.DESTINATION_CHOICES,
        default=constants.DESTINATION_UNASSIGNED, verbose_name='处理去向',
    )
    handling_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_handling_owned', verbose_name='处理人',
    )
    handling_action = models.TextField(blank=True, verbose_name='处理动作')
    handling_note = models.TextField(blank=True, verbose_name='处理说明')
    current_review = models.ForeignKey(
        'FeedbackReview', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='current_for_tickets', verbose_name='当前复核结论',
    )

    effect_status = models.CharField(
        max_length=24, choices=constants.EFFECT_CHOICES,
        default=constants.EFFECT_NOT_ASSESSED, verbose_name='教学效果状态',
    )
    effect_note = models.TextField(blank=True, verbose_name='教学效果说明')
    retest_fact_ref = models.CharField(max_length=96, blank=True, verbose_name='复测事实 ID')
    retest_attempt_ref = models.CharField(max_length=128, blank=True, verbose_name='复测尝试引用')
    effect_updated_at = models.DateTimeField(null=True, blank=True, verbose_name='效果更新时间')

    submitted_at = models.DateTimeField(default=timezone.now, verbose_name='服务端接收时间')
    deduplicated_at = models.DateTimeField(null=True, blank=True, verbose_name='去重完成时间')
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='最近复核时间')
    handling_started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始处理时间')
    handled_at = models.DateTimeField(null=True, blank=True, verbose_name='处理完成时间')
    reopened_at = models.DateTimeField(null=True, blank=True, verbose_name='最近重开时间')
    last_evidence_at = models.DateTimeField(null=True, blank=True, verbose_name='最近补证时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '反馈工单'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['submitter', 'client_request_id'],
                name='feedback_unique_client_request',
            ),
        ]
        indexes = [
            models.Index(fields=['status', 'category', '-created_at']),
            models.Index(fields=['student', '-created_at']),
            models.Index(fields=['attempt', 'category']),
            models.Index(fields=['dedup_key']),
            models.Index(fields=['owner', 'status']),
        ]

    def __str__(self):
        return f'{self.feedback_id} {self.category}/{self.issue_type} {self.status}'

    @property
    def evidence_complete(self):
        return not self.missing_evidence

    @property
    def mapping_complete(self):
        """Whether the ticket can locate task, attempt, version and target.

        An external attempt reference is deliberately not enough: phase 3
        candidates must be able to re-open the original attempt.  Unmapped
        tickets remain readable and can be reviewed, but cannot feed candidate
        acceptance or capability statistics.
        """

        return bool(
            self.catalog_id
            and self.task_id
            and self.attempt_id
            and (self.capability_id or self.knowledge_point_id)
        )

    @property
    def candidate_eligible(self):
        if self.duplicate_of_id:
            return False
        if self.status not in constants.CANDIDATE_SOURCE_STATUSES:
            return False
        return self.evidence_complete and self.mapping_complete

    @property
    def waiting_days(self):
        if not self.created_at:
            return 0
        return max(0, (timezone.now() - self.created_at).days)

    @property
    def priority_reason(self):
        parts = []
        if self.conflict_flag:
            parts.append('证据冲突')
        if self.impact_level != constants.IMPACT_UNKNOWN:
            parts.append(f'影响{constants.IMPACT_LABELS.get(self.impact_level, self.impact_level)}')
        if self.novelty == constants.NOVELTY_NEW:
            parts.append('新问题')
        parts.append(f'等待{self.waiting_days}天')
        return '；'.join(parts)

    @property
    def production_effects(self):
        return {
            'export_triggered': False,
            'quota_reserved': False,
            'policy_changed': False,
            'candidate_created': False,
            'rule_effective': False,
        }


class FeedbackAttachment(models.Model):
    attachment_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='附件 ID')
    ticket = models.ForeignKey(
        FeedbackTicket, on_delete=models.CASCADE, related_name='attachments', verbose_name='反馈工单',
    )
    file = models.FileField(upload_to=feedback_attachment_path, verbose_name='受控文件')
    original_name = models.CharField(max_length=255, verbose_name='原始文件名')
    content_type = models.CharField(max_length=128, blank=True, verbose_name='内容类型')
    size = models.PositiveBigIntegerField(default=0, verbose_name='字节数')
    sha256 = models.CharField(max_length=64, blank=True, verbose_name='内容摘要')
    visibility = models.CharField(
        max_length=16, choices=constants.VISIBILITY_CHOICES,
        default=constants.VISIBILITY_STUDENT, verbose_name='可见范围',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_attachments_uploaded', verbose_name='上传人',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='上传时间')

    class Meta:
        verbose_name = '反馈受控附件'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.attachment_id} {self.original_name}'


class FeedbackEvidence(models.Model):
    evidence_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='证据 ID')
    ticket = models.ForeignKey(
        FeedbackTicket, on_delete=models.CASCADE, related_name='evidence', verbose_name='反馈工单',
    )
    slot = models.CharField(max_length=64, verbose_name='证据槽')
    ref = models.CharField(max_length=255, blank=True, verbose_name='证据引用')
    version = models.CharField(max_length=64, blank=True, verbose_name='证据版本')
    summary = models.TextField(blank=True, verbose_name='必要摘要')
    attachment = models.ForeignKey(
        FeedbackAttachment, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='evidence_rows', verbose_name='受控附件',
    )
    status = models.CharField(
        max_length=16, choices=constants.EVIDENCE_STATUS_CHOICES,
        default=constants.EVIDENCE_STATUS_MISSING, verbose_name='证据状态',
    )
    source = models.CharField(
        max_length=16, choices=constants.EVIDENCE_SOURCE_CHOICES,
        default=constants.EVIDENCE_SOURCE_SUBMITTER, verbose_name='证据来源',
    )
    visibility = models.CharField(
        max_length=16, choices=constants.VISIBILITY_CHOICES,
        default=constants.VISIBILITY_STUDENT, verbose_name='可见范围',
    )
    is_current = models.BooleanField(default=True, verbose_name='当前版本')
    supersedes = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='superseded_by', verbose_name='替代的旧证据',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_evidence_created', verbose_name='记录人',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '反馈证据'
        verbose_name_plural = verbose_name
        ordering = ['slot', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['ticket', 'slot'],
                condition=models.Q(is_current=True),
                name='feedback_one_current_evidence',
            ),
        ]
        indexes = [
            models.Index(fields=['ticket', 'is_current']),
            models.Index(fields=['slot', 'status']),
        ]

    def __str__(self):
        return f'{self.slot}={self.status}'

    def clean(self):
        if self.attachment_id and self.attachment.ticket_id != self.ticket_id:
            raise ValidationError({'attachment': '附件不属于该反馈工单。'})


class FeedbackReview(models.Model):
    """Append-only fact-review conclusion.

    ``is_current`` is the only mutable flag.  A correction creates a new row and
    marks the old one non-current; the old reason, reviewer and original
    decision snapshot stay intact.
    """

    review_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='复核 ID')
    ticket = models.ForeignKey(
        FeedbackTicket, on_delete=models.CASCADE, related_name='reviews', verbose_name='反馈工单',
    )
    conclusion = models.CharField(
        max_length=16,
        choices=[(constants.STATUS_CONFIRMED, '已确认'), (constants.STATUS_REJECTED, '已驳回')],
        verbose_name='复核结论',
    )
    reason = models.TextField(verbose_name='复核理由')
    evidence_refs = models.JSONField(default=list, blank=True, verbose_name='引用证据')
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='feedback_reviews', verbose_name='复核人',
    )
    reviewer_role = models.CharField(max_length=16, verbose_name='复核人角色快照')
    original_decision_snapshot = models.JSONField(default=dict, blank=True, verbose_name='原始判定快照')
    supersedes = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='superseded_by_reviews', verbose_name='替代的复核',
    )
    is_current = models.BooleanField(default=True, verbose_name='当前结论')
    ticket_version = models.PositiveIntegerField(verbose_name='复核时工单版本')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='复核时间')

    class Meta:
        verbose_name = '反馈复核结论'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['ticket'],
                condition=models.Q(is_current=True),
                name='feedback_one_current_review',
            ),
        ]

    def __str__(self):
        return f'{self.ticket_id} {self.conclusion} v{self.ticket_version}'

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('复核结论只追加，不能修改；请新增复核版本。')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('复核结论只追加，不能删除。')


class FeedbackAction(models.Model):
    """Append-only action log for every ticket transition and access note."""

    action_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='动作 ID')
    ticket = models.ForeignKey(
        FeedbackTicket, on_delete=models.CASCADE, related_name='actions', verbose_name='反馈工单',
    )
    action = models.CharField(max_length=48, verbose_name='动作')
    from_status = models.CharField(max_length=24, blank=True, verbose_name='原状态')
    to_status = models.CharField(max_length=24, blank=True, verbose_name='新状态')
    event_type = models.CharField(max_length=32, blank=True, verbose_name='对应学习事件类型')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_actions', verbose_name='操作人',
    )
    actor_role = models.CharField(max_length=16, blank=True, verbose_name='操作人角色')
    reason = models.TextField(blank=True, verbose_name='理由')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='动作摘要')
    visibility = models.CharField(
        max_length=16, choices=constants.VISIBILITY_CHOICES,
        default=constants.VISIBILITY_STUDENT, verbose_name='可见范围',
    )
    ticket_version = models.PositiveIntegerField(default=1, verbose_name='动作后工单版本')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='动作时间')

    class Meta:
        verbose_name = '反馈处理动作'
        verbose_name_plural = verbose_name
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['ticket', 'created_at'])]

    def __str__(self):
        return f'{self.ticket_id} {self.action} -> {self.to_status}'

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('反馈动作只追加，不能修改。')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('反馈动作只追加，不能删除。')


class FeedbackReferral(models.Model):
    referral_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='转交 ID')
    ticket = models.ForeignKey(
        FeedbackTicket, on_delete=models.CASCADE, related_name='referrals', verbose_name='反馈工单',
    )
    destination = models.CharField(
        max_length=32, choices=constants.DESTINATION_CHOICES, verbose_name='转交去向',
    )
    note = models.TextField(blank=True, verbose_name='转交说明')
    external_ref = models.CharField(max_length=255, blank=True, verbose_name='接收方引用')
    status = models.CharField(
        max_length=16, choices=constants.REFERRAL_STATUS_CHOICES,
        default=constants.REFERRAL_PENDING, verbose_name='接收状态',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_referrals_created', verbose_name='转交人',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='转交时间')
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_referrals_acknowledged', verbose_name='确认人',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True, verbose_name='确认时间')
    ack_note = models.TextField(blank=True, verbose_name='确认说明')

    class Meta:
        verbose_name = '反馈转交'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.ticket_id} -> {self.destination} ({self.status})'


class FeedbackRelation(models.Model):
    relation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='关联 ID')
    from_ticket = models.ForeignKey(
        FeedbackTicket, on_delete=models.CASCADE, related_name='relations_from', verbose_name='来源反馈',
    )
    to_ticket = models.ForeignKey(
        FeedbackTicket, on_delete=models.CASCADE, related_name='relations_to', verbose_name='目标反馈',
    )
    relation_type = models.CharField(max_length=32, verbose_name='关联类型')
    note = models.TextField(blank=True, verbose_name='说明')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_relations_created', verbose_name='创建人',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '反馈关联'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['from_ticket', 'to_ticket', 'relation_type'],
                name='feedback_unique_relation',
            ),
        ]

    def __str__(self):
        return f'{self.from_ticket_id} -{self.relation_type}-> {self.to_ticket_id}'


class FeedbackSamplingBatch(models.Model):
    batch_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='抽查批次 ID')
    scope = models.JSONField(default=dict, verbose_name='抽样范围')
    population_count = models.PositiveIntegerField(default=0, verbose_name='总体数量')
    population_hash = models.CharField(max_length=64, blank=True, verbose_name='总体摘要')
    population_ids = models.JSONField(default=list, verbose_name='总体 ID 快照')
    sample_size = models.PositiveIntegerField(default=0, verbose_name='目标样本数')
    random_seed = models.BigIntegerField(default=0, verbose_name='随机种子')
    method = models.CharField(max_length=16, default=constants.SAMPLING_RANDOM, verbose_name='抽样方法')
    exclude_prior = models.BooleanField(default=True, verbose_name='排除既往样本')
    notes = models.TextField(blank=True, verbose_name='抽样依据/说明')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_sampling_created', verbose_name='创建人',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '反馈随机抽查批次'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.batch_id} seed={self.random_seed} n={self.sample_size}'


class FeedbackSamplingItem(models.Model):
    batch = models.ForeignKey(
        FeedbackSamplingBatch, on_delete=models.CASCADE, related_name='items', verbose_name='抽查批次',
    )
    ticket = models.ForeignKey(
        FeedbackTicket, on_delete=models.CASCADE, related_name='sampling_items', verbose_name='反馈工单',
    )
    selected_reason = models.CharField(
        max_length=16, choices=constants.SAMPLING_REASON_CHOICES, verbose_name='入选原因',
    )
    ticket_version = models.PositiveIntegerField(default=1, verbose_name='抽样时工单版本')
    rank = models.PositiveIntegerField(default=0, verbose_name='顺序')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '反馈抽查项'
        verbose_name_plural = verbose_name
        ordering = ['rank', 'id']
        constraints = [
            models.UniqueConstraint(fields=['batch', 'ticket'], name='feedback_unique_sampling_item'),
        ]

    def __str__(self):
        return f'{self.batch_id} {self.ticket_id} {self.selected_reason}'


class FeedbackAccessLog(models.Model):
    ticket = models.ForeignKey(
        FeedbackTicket, on_delete=models.CASCADE, related_name='access_logs', verbose_name='反馈工单',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='feedback_access_logs', verbose_name='访问人',
    )
    action = models.CharField(max_length=32, verbose_name='访问动作')
    allowed = models.BooleanField(default=True, verbose_name='是否允许')
    note = models.CharField(max_length=255, blank=True, verbose_name='说明')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='访问时间')

    class Meta:
        verbose_name = '反馈访问日志'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.ticket_id} {self.action} allowed={self.allowed}'


class FeedbackEventLink(models.Model):
    """Outbox row linking one business action to the shared LearningEvent store.

    The event ID is deterministic.  A retry returns the original event instead
    of creating a second learning fact.  A mismatch is shown to teachers and is
    never silently overwritten.
    """

    ticket = models.ForeignKey(
        FeedbackTicket, on_delete=models.CASCADE, related_name='event_links', verbose_name='反馈工单',
    )
    action = models.ForeignKey(
        FeedbackAction, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='event_links', verbose_name='对应动作',
    )
    event_id = models.CharField(max_length=96, unique=True, verbose_name='事件 ID')
    event_type = models.CharField(max_length=32, verbose_name='事件类型')
    status = models.CharField(
        max_length=16, choices=constants.EVENT_LINK_STATUS_CHOICES,
        default=constants.EVENT_LINK_PENDING, verbose_name='关联状态',
    )
    attempts = models.PositiveIntegerField(default=0, verbose_name='同步尝试次数')
    last_error = models.CharField(max_length=255, blank=True, verbose_name='最后错误摘要')
    checked_at = models.DateTimeField(null=True, blank=True, verbose_name='最近核对时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '反馈事件关联'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['ticket', 'status']),
        ]

    def __str__(self):
        return f'{self.event_id} {self.status}'
