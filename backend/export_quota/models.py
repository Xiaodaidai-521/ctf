"""Quota reservation reference implementation (regex spec H6; review R2).

The **shared** `QuotaBucket` row is the lock object: reserve locks the bucket,
not the per-reservation row, so two concurrent reservations against the same
bucket cannot both pass (locking your own reservation row would not prevent
over-reservation). Accounting keeps settled / active-reserved / unknown-reserved
separate so an expired-with-unknown-result reservation is not blindly released.

Non-production authority until a real quota owner is wired (decision 1/4).
"""

from django.db import models
from django.utils import timezone


class QuotaBucket(models.Model):
    """A shared quota account for (subject, data_domain, window)."""

    subject_id = models.CharField(max_length=160, verbose_name='主体')
    data_domain = models.CharField(max_length=120, verbose_name='数据域')
    window_key = models.CharField(max_length=80, verbose_name='窗口键')
    limit = models.BigIntegerField(verbose_name='额度上限')
    settled = models.BigIntegerField(default=0, verbose_name='已结算')
    active_reserved = models.BigIntegerField(default=0, verbose_name='有效占用')
    unknown_reserved = models.BigIntegerField(default=0, verbose_name='结果未知占用')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '配额桶'
        verbose_name_plural = '配额桶'
        constraints = [
            models.UniqueConstraint(
                fields=['subject_id', 'data_domain', 'window_key'], name='unique_quota_bucket'
            )
        ]

    @property
    def committed_and_held(self) -> int:
        return self.settled + self.active_reserved + self.unknown_reserved

    @property
    def available(self) -> int:
        return self.limit - self.committed_and_held

    def __str__(self):
        return f'{self.subject_id}/{self.data_domain}/{self.window_key}'


class QuotaReservation(models.Model):
    """One reservation against a bucket, with an explicit lifecycle state."""

    STATE = [('reserved', '预占'), ('committed', '已结算'),
             ('released', '已释放'), ('unknown', '结果未知')]

    reservation_id = models.CharField(max_length=160, unique=True, verbose_name='预占ID')
    bucket = models.ForeignKey(QuotaBucket, on_delete=models.PROTECT, related_name='reservations',
                               verbose_name='配额桶')
    amount = models.BigIntegerField(verbose_name='预占量')
    settled_amount = models.BigIntegerField(default=0, verbose_name='结算量')
    state = models.CharField(max_length=20, choices=STATE, default='reserved', db_index=True, verbose_name='状态')
    request_fingerprint = models.CharField(max_length=64, verbose_name='请求指纹')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='过期时间')

    class Meta:
        verbose_name = '配额预占'
        verbose_name_plural = '配额预占'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reservation_id}:{self.state}:{self.amount}'
