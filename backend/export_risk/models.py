"""Persistence for M1: trusted behaviour events and the request/delivery counts.

Three counts are kept in **separate** tables with distinct write paths (E5):
request volume (attempts, includes rejected), reservation volume (export_quota,
M4) and delivery volume (execution telemetry, carries ``is_simulated``). This
module imports Django; it is the persistence layer, kept out of ``judgment/``.
Subjects/recipients are external string ids — no FK to users (low coupling).
"""

from django.db import models
from django.utils import timezone


class BehaviorEvent(models.Model):
    """A trusted behaviour event (query/export/denial/delivery/share access).

    `event_id` is unique for idempotent ingestion dedup (E4). `occurred_at` and
    `received_at` are kept distinct so windows can use the correct time basis and
    a watermark can be derived from the max processed `received_at`.
    """

    EVENT_TYPES = [
        ('query', '查询'),
        ('export_request', '外发请求'),
        ('denial', '拒绝'),
        ('delivery', '交付'),
        ('share_access', '共享访问'),
    ]

    event_id = models.CharField(max_length=160, unique=True, verbose_name='事件ID')
    subject_id = models.CharField(max_length=160, db_index=True, verbose_name='主体')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, db_index=True, verbose_name='事件类型')
    occurred_at = models.DateTimeField(db_index=True, verbose_name='发生时间')
    received_at = models.DateTimeField(db_index=True, verbose_name='接收时间')
    source = models.CharField(max_length=80, verbose_name='来源')
    object_scope = models.JSONField(default=list, blank=True, verbose_name='对象范围')
    recipient_id = models.CharField(max_length=160, blank=True, verbose_name='接收者')
    record_count = models.IntegerField(default=0, verbose_name='记录数')
    is_simulated = models.BooleanField(default=False, db_index=True, verbose_name='是否模拟')
    payload = models.JSONField(default=dict, blank=True, verbose_name='附加载荷')

    class Meta:
        verbose_name = '行为事件'
        verbose_name_plural = '行为事件'
        ordering = ['occurred_at', 'id']
        indexes = [
            models.Index(fields=['subject_id', 'event_type', 'occurred_at']),
            models.Index(fields=['received_at']),
        ]

    def __str__(self):
        return f'{self.event_type}:{self.subject_id}@{self.occurred_at}'


class ExportRequestLog(models.Model):
    """Request volume — one row per export attempt, **including rejected** (E5)."""

    request_id = models.CharField(max_length=160, db_index=True, verbose_name='请求ID')
    revision = models.CharField(max_length=40, default='1', verbose_name='修订号')
    subject_id = models.CharField(max_length=160, db_index=True, verbose_name='主体')
    asset_version = models.CharField(max_length=80, verbose_name='资产版本')
    scope = models.JSONField(default=list, blank=True, verbose_name='范围')
    operation = models.CharField(max_length=40, verbose_name='操作')
    recipient_id = models.CharField(max_length=160, blank=True, verbose_name='接收者')
    purpose = models.CharField(max_length=200, blank=True, verbose_name='用途')
    business_task_id = models.CharField(max_length=160, blank=True, verbose_name='业务任务')
    request_fingerprint = models.CharField(max_length=64, db_index=True, verbose_name='请求指纹')
    record_count = models.IntegerField(default=0, verbose_name='记录数')
    recommended_action = models.CharField(max_length=20, blank=True, verbose_name='建议动作')
    rejected = models.BooleanField(default=False, db_index=True, verbose_name='是否被拒')
    environment = models.CharField(max_length=20, default='production', verbose_name='环境')
    source_mode = models.CharField(max_length=20, default='synthetic', verbose_name='来源模式')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='记录时间')

    class Meta:
        verbose_name = '外发请求记录'
        verbose_name_plural = '外发请求记录'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['subject_id', 'created_at'])]

    def __str__(self):
        return f'{self.request_id}#{self.revision}'


class DeliveryRecord(models.Model):
    """Delivery volume — written only by execution telemetry (E5/I6).

    `is_simulated` is a data property, not a report-time disclaimer: a simulated
    ledger can never be mistaken for real delivery telemetry.
    """

    delivery_id = models.CharField(max_length=160, unique=True, verbose_name='交付ID')
    request_id = models.CharField(max_length=160, db_index=True, verbose_name='请求ID')
    subject_id = models.CharField(max_length=160, db_index=True, verbose_name='主体')
    recipient_id = models.CharField(max_length=160, blank=True, verbose_name='接收者')
    delivered_record_count = models.IntegerField(default=0, verbose_name='实际交付记录数')
    is_simulated = models.BooleanField(default=True, db_index=True, verbose_name='是否模拟账本')
    occurred_at = models.DateTimeField(db_index=True, verbose_name='交付时间')
    source = models.CharField(max_length=80, default='', verbose_name='遥测来源')

    class Meta:
        verbose_name = '交付记录'
        verbose_name_plural = '交付记录'
        ordering = ['-occurred_at']

    def __str__(self):
        return f'{self.delivery_id} sim={self.is_simulated}'


class RiskDecision(models.Model):
    """Persisted, **immutable** decision (regex spec H3).

    History is never overwritten; a correction creates a new row linked via
    `supersedes`. Status may transition to superseded/invalidated, but the record
    and its bindings stay intact for audit/replay.
    """

    STATUS = [('valid', '有效'), ('superseded', '被替代'), ('invalidated', '已失效')]

    decision_id = models.CharField(max_length=160, unique=True, verbose_name='决策ID')
    assessment_id = models.CharField(max_length=160, blank=True, verbose_name='研判ID')
    request_id = models.CharField(max_length=160, db_index=True, verbose_name='请求ID')
    request_fingerprint = models.CharField(max_length=64, db_index=True, verbose_name='请求指纹')
    asset_version = models.CharField(max_length=80, verbose_name='资产版本')
    profile_id = models.CharField(max_length=160, blank=True, verbose_name='画像ID')
    scope = models.JSONField(default=list, blank=True, verbose_name='范围')
    action = models.CharField(max_length=20, verbose_name='动作')
    obligations = models.JSONField(default=list, blank=True, verbose_name='义务')
    policy_version = models.CharField(max_length=80, verbose_name='政策版本')
    model_version = models.CharField(max_length=80, blank=True, verbose_name='模型版本')
    feature_set_version = models.CharField(max_length=80, blank=True, verbose_name='特征集版本')
    issued_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name='签发时间')
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name='有效期至')
    status = models.CharField(max_length=20, choices=STATUS, default='valid', db_index=True, verbose_name='状态')
    supersedes = models.CharField(max_length=160, blank=True, verbose_name='替代的决策ID')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='记录时间')

    class Meta:
        verbose_name = '风险决策'
        verbose_name_plural = '风险决策'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['request_fingerprint', 'status'])]

    def __str__(self):
        return f'{self.decision_id}:{self.action}:{self.status}'


class IdempotencyRecord(models.Model):
    """Idempotency key bound to a request/decision/plan/obligations digest (R1).

    Replay with the same key returns `result_ref`; a different `bound_digest`
    under the same key is a conflict. The stored result is a reference, not a
    final verdict, so execution still re-checks current conditions on replay.
    """

    key = models.CharField(max_length=200, unique=True, verbose_name='幂等键')
    operation = models.CharField(max_length=40, verbose_name='操作')
    request_fingerprint = models.CharField(max_length=64, verbose_name='请求指纹')
    bound_digest = models.CharField(max_length=64, verbose_name='绑定摘要')
    result_ref = models.CharField(max_length=160, verbose_name='结果引用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='记录时间')

    class Meta:
        verbose_name = '幂等记录'
        verbose_name_plural = '幂等记录'

    def __str__(self):
        return f'{self.operation}:{self.key}'


class ExecutionAuthorizationRecord(models.Model):
    """Authorization state machine (review R1).

    valid -> claiming -> consumed; or valid -> expired/revoked. Terminal states
    never return to valid; a re-evaluation issues a new authorization_id.
    """

    STATE = [('valid', '有效'), ('claiming', '领取中'), ('consumed', '已消费'),
             ('expired', '已过期'), ('revoked', '已撤销')]

    authorization_id = models.CharField(max_length=160, unique=True, verbose_name='授权ID')
    decision_id = models.CharField(max_length=160, db_index=True, verbose_name='决策ID')
    request_fingerprint = models.CharField(max_length=64, verbose_name='请求指纹')
    state = models.CharField(max_length=20, choices=STATE, default='valid', db_index=True, verbose_name='状态')
    execution_id = models.CharField(max_length=160, blank=True, verbose_name='执行ID')
    reservation_id = models.CharField(max_length=160, blank=True, verbose_name='预占ID')
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name='有效期至')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    consumed_at = models.DateTimeField(null=True, blank=True, verbose_name='消费时间')

    class Meta:
        verbose_name = '执行授权'
        verbose_name_plural = '执行授权'

    def __str__(self):
        return f'{self.authorization_id}:{self.state}'


class EventOutbox(models.Model):
    """Transactional outbox for decision-level events (regex spec H7).

    Written in the same transaction as the business state; a relay drains
    pending rows. `event_id` unique gives at-least-once consumers a dedup key.
    """

    STATUS = [('pending', '待发'), ('sent', '已发')]

    event_id = models.CharField(max_length=200, unique=True, verbose_name='事件ID')
    event_type = models.CharField(max_length=60, db_index=True, verbose_name='事件类型')
    payload = models.JSONField(default=dict, blank=True, verbose_name='载荷')
    status = models.CharField(max_length=20, choices=STATUS, default='pending', db_index=True, verbose_name='状态')
    ledger_hash = models.CharField(max_length=64, blank=True, verbose_name='台账哈希')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='创建时间')
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='发送时间')

    class Meta:
        verbose_name = '事件发件箱'
        verbose_name_plural = '事件发件箱'
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.event_type}:{self.event_id}:{self.status}'
