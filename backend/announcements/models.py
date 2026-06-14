from django.db import models
from django.contrib.auth import get_user_model
from users.models import CTFUser

User = get_user_model()


class Announcement(models.Model):
    """平台公告模型"""

    PRIORITY_CHOICES = [
        ('low', '普通'),
        ('medium', '重要'),
        ('high', '紧急'),
    ]

    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('published', '已发布'),
        ('archived', '已归档'),
    ]

    title = models.CharField('标题', max_length=200)
    content = models.TextField('内容')
    priority = models.CharField(
        '优先级',
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='low',
        help_text='公告优先级，紧急公告会以特殊样式显示'
    )
    status = models.CharField(
        '状态',
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft',
        help_text='公告状态'
    )
    is_pinned = models.BooleanField('是否置顶', default=False, help_text='置顶的公告会始终显示在列表顶部')
    author = models.ForeignKey(
        CTFUser,
        on_delete=models.CASCADE,
        verbose_name='发布者',
        related_name='announcements'
    )
    view_count = models.PositiveIntegerField('浏览次数', default=0)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    published_at = models.DateTimeField('发布时间', null=True, blank=True)

    class Meta:
        db_table = 'announcements'
        verbose_name = '平台公告'
        verbose_name_plural = verbose_name
        ordering = ['-is_pinned', '-published_at', '-created_at']

    def __str__(self):
        return self.title

    def increment_view(self):
        """增加浏览次数"""
        self.view_count += 1
        self.save(update_fields=['view_count'])
