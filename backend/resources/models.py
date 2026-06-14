from django.db import models
from users.models import CTFUser


class Resource(models.Model):
    """学习资源模型"""
    RESOURCE_TYPE_CHOICES = [
        ('document', '文档'),
        ('video', '视频'),
        ('report', '报告'),
        ('zip', '压缩包'),
    ]

    STATUS_CHOICES = [
        ('pending', '待审核'),
        ('approved', '已通过'),
        ('rejected', '已拒绝'),
    ]

    title = models.CharField(max_length=200, verbose_name='资源标题')
    description = models.TextField(verbose_name='资源描述')
    resource_type = models.CharField(
        max_length=20,
        choices=RESOURCE_TYPE_CHOICES,
        verbose_name='资源类型'
    )
    file = models.FileField(upload_to='resources/', verbose_name='资源文件')
    file_size = models.IntegerField(default=0, verbose_name='文件大小(字节)')
    cover_image = models.ImageField(
        upload_to='resource_covers/',
        blank=True,
        null=True,
        verbose_name='封面图片'
    )
    category = models.CharField(max_length=100, verbose_name='资源分类')
    tags = models.CharField(max_length=200, blank=True, verbose_name='标签（逗号分隔）')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='审核状态'
    )
    uploader = models.ForeignKey(
        CTFUser,
        on_delete=models.CASCADE,
        related_name='uploaded_resources',
        verbose_name='上传者'
    )
    reviewer = models.ForeignKey(
        CTFUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_resources',
        verbose_name='审核人'
    )
    review_comment = models.TextField(blank=True, verbose_name='审核意见')
    view_count = models.IntegerField(default=0, verbose_name='查看次数')
    download_count = models.IntegerField(default=0, verbose_name='下载次数')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='审核时间')

    class Meta:
        verbose_name = '学习资源'
        verbose_name_plural = '学习资源'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_resource_type_display()})"

    def get_tags_list(self):
        """获取标签列表"""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',')]
        return []

    def increment_view_count(self):
        """增加查看次数"""
        self.view_count += 1
        self.save(update_fields=['view_count'])

    def increment_download_count(self):
        """增加下载次数"""
        self.download_count += 1
        self.save(update_fields=['download_count'])
