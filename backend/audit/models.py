# audit/models.py
# -*- coding: utf-8 -*-
"""Audit models for platform events, AI calls, and tamper-evident ledger entries."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    """Generic audit event for important platform actions."""

    CATEGORY_CHOICES = [
        ('ai_call', 'AI 调用'),
        ('flag_submit', 'Flag 提交'),
        ('auth', '认证登录'),
        ('admin_action', '管理操作'),
        ('exception', '异常请求'),
        ('container', '容器操作'),
        ('legal_analysis', '法律合规分析'),
        ('kb_ingestion', '知识库入库'),
        ('report_export', '报告导出'),
        ('consent_sign', '协议签署'),
        ('data_processing', '数据处理'),
        ('violation_record', '违规记录'),
        ('risk_override', '风险覆盖'),
        ('compliance_exercise', '合规演练'),
    ]

    LEVEL_CHOICES = [
        ('INFO', '信息'),
        ('WARNING', '警告'),
        ('ERROR', '错误'),
        ('CRITICAL', '严重'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='操作用户',
    )
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        db_index=True,
        verbose_name='事件类别',
    )
    level = models.CharField(
        max_length=10,
        choices=LEVEL_CHOICES,
        default='INFO',
        verbose_name='严重级别',
    )
    summary = models.CharField(max_length=200, verbose_name='事件摘要')
    detail = models.JSONField(default=dict, blank=True, verbose_name='详细信息')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP 地址')
    user_agent = models.CharField(max_length=500, blank=True, verbose_name='User-Agent')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='发生时间')

    class Meta:
        verbose_name = '审计事件'
        verbose_name_plural = '审计事件'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category', 'created_at']),
            models.Index(fields=['user', 'category']),
            models.Index(fields=['level']),
        ]

    def __str__(self):
        return f'[{self.level}] {self.summary}'

    @classmethod
    def log(cls, category, summary, level='INFO', user=None, detail=None, request=None):
        """Create an audit event with optional request metadata."""
        kwargs = {
            'category': category,
            'summary': summary,
            'level': level,
        }
        if user:
            kwargs['user'] = user
        if detail:
            kwargs['detail'] = detail
        if request:
            kwargs['ip_address'] = cls._get_client_ip(request)
            kwargs['user_agent'] = request.META.get('HTTP_USER_AGENT', '')[:500]
        return cls.objects.create(**kwargs)

    @staticmethod
    def _get_client_ip(request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class AuditLedgerEntry(models.Model):
    """Tamper-evident audit ledger entry backed by a hash chain."""

    event_category = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name='Event category',
    )
    object_type = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name='Object type',
    )
    object_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name='Object ID',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_ledger_entries',
        verbose_name='Actor',
    )
    payload = models.JSONField(default=dict, blank=True, verbose_name='Payload')
    payload_hash = models.CharField(max_length=64, verbose_name='Payload hash')
    previous_hash = models.CharField(max_length=64, blank=True, verbose_name='Previous hash')
    current_hash = models.CharField(max_length=64, unique=True, verbose_name='Current hash')
    chain_version = models.CharField(max_length=20, default='v1', verbose_name='Chain version')
    created_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name='Created at')

    class Meta:
        verbose_name = 'Audit ledger entry'
        verbose_name_plural = 'Audit ledger entries'
        ordering = ['id']
        indexes = [
            models.Index(fields=['event_category', 'created_at']),
            models.Index(fields=['object_type', 'object_id']),
            models.Index(fields=['actor', 'created_at']),
        ]

    def __str__(self):
        return f'{self.id}: {self.event_category} {self.current_hash[:12]}'


class AuditLedgerLock(models.Model):
    """Singleton lock row used to serialize audit hash-chain appends."""

    key = models.CharField(max_length=50, unique=True, default='default')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Audit ledger lock'
        verbose_name_plural = 'Audit ledger locks'

    def __str__(self):
        return self.key


class AIAuditLog(models.Model):
    """Specialized audit log for AI provider calls."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='调用用户',
    )
    challenge = models.ForeignKey(
        'challenges.Challenge',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='关联题目',
    )
    provider = models.CharField(max_length=50, verbose_name='AI 厂商')
    model = models.CharField(max_length=100, verbose_name='模型名称')
    user_message = models.TextField(verbose_name='用户输入')
    ai_response = models.TextField(blank=True, verbose_name='AI 响应')
    mode = models.CharField(max_length=20, blank=True, verbose_name='调用模式')
    success = models.BooleanField(default=True, verbose_name='是否成功')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    duration_ms = models.IntegerField(default=0, verbose_name='耗时(毫秒)')
    token_estimate = models.IntegerField(default=0, verbose_name='令牌数估算')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='调用时间')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP 地址')

    class Meta:
        verbose_name = 'AI 调用日志'
        verbose_name_plural = 'AI 调用日志'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['challenge', 'created_at']),
            models.Index(fields=['provider', 'created_at']),
        ]

    def __str__(self):
        return f'{self.provider}/{self.model} - {self.created_at}'

    @classmethod
    def log_ai_call(cls, user, provider, model, user_message, ai_response='',
                    mode='', success=True, error_message='', duration_ms=0,
                    token_estimate=0, challenge=None, request=None):
        """Create an AI audit log entry."""
        kwargs = {
            'user': user,
            'provider': provider,
            'model': model,
            'user_message': user_message[:5000] if user_message else '',
            'ai_response': ai_response[:10000] if ai_response else '',
            'mode': mode,
            'success': success,
            'error_message': error_message,
            'duration_ms': duration_ms,
            'token_estimate': token_estimate,
            'challenge': challenge,
        }
        if request:
            kwargs['ip_address'] = AuditEvent._get_client_ip(request)
        return cls.objects.create(**kwargs)
