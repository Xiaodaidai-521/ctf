from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class LearningInsight(models.Model):
    INSIGHT_TYPE_CHOICES = [
        ('strength', '优势'),
        ('weakness', '薄弱'),
        ('plateau', '平台期'),
        ('acceleration', '加速'),
        ('recommendation', '推荐'),
    ]
    SEVERITY_CHOICES = [
        ('info', '信息'),
        ('warning', '警告'),
        ('critical', '严重'),
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learning_insights',
        verbose_name='学生'
    )
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPE_CHOICES, verbose_name='洞察类型')
    concept = models.ForeignKey(
        'learning_paths.KnowledgeConcept',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='insights',
        verbose_name='关联概念'
    )
    title = models.CharField(max_length=200, verbose_name='标题')
    description = models.TextField(verbose_name='描述')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, verbose_name='严重程度')
    actionable = models.BooleanField(default=True, verbose_name='是否可执行')
    action_link = models.CharField(max_length=500, blank=True, verbose_name='行动链接')
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name='生成时间')
    acknowledged_at = models.DateTimeField(null=True, blank=True, verbose_name='确认时间')

    class Meta:
        verbose_name = '学习洞察'
        verbose_name_plural = verbose_name
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['student', '-generated_at']),
            models.Index(fields=['student', 'acknowledged_at']),
        ]

    def __str__(self):
        return f"{self.student.username} - {self.get_insight_type_display()}: {self.title}"


class WeeklyLearningSummary(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='weekly_summaries',
        verbose_name='学生'
    )
    week_start = models.DateField(verbose_name='周开始日期')
    total_study_minutes = models.IntegerField(default=0, verbose_name='总学习时长(分钟)')
    modules_completed = models.IntegerField(default=0, verbose_name='完成模块数')
    exercises_completed = models.IntegerField(default=0, verbose_name='完成练习数')
    concepts_mastered = models.JSONField(default=dict, verbose_name='掌握概念')
    ai_interactions = models.IntegerField(default=0, verbose_name='AI交互次数')
    sandbox_executions = models.IntegerField(default=0, verbose_name='沙箱执行次数')
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name='生成时间')

    class Meta:
        verbose_name = '每周学习总结'
        verbose_name_plural = verbose_name
        ordering = ['-week_start']
        unique_together = ('student', 'week_start')
        indexes = [
            models.Index(fields=['student', '-week_start']),
        ]

    def __str__(self):
        return f"{self.student.username} - 第{self.week_start}周"


class AdminLearningScore(models.Model):
    """管理员对学生阶段学习状态的人工评分。"""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_learning_scores',
        verbose_name='学生',
    )
    scored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='submitted_learning_scores',
        verbose_name='评分管理员',
    )
    measured_at = models.DateField(verbose_name='实际测评日期')
    total_score = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='总分')
    dimension_scores = models.JSONField(default=dict, blank=True, verbose_name='分项评分')
    tags = models.JSONField(default=list, blank=True, verbose_name='评分标签')
    remark = models.TextField(blank=True, verbose_name='评分备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='录入时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '管理员学习评分'
        verbose_name_plural = verbose_name
        ordering = ['-measured_at', '-created_at']
        indexes = [
            models.Index(fields=['student', '-measured_at']),
            models.Index(fields=['scored_by', '-created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_score__gte=0) & models.Q(total_score__lte=100),
                name='admin_learning_score_total_0_100',
            ),
        ]

    def clean(self):
        if self.measured_at and self.measured_at > timezone.localdate():
            raise ValidationError({'measured_at': '实际测评日期不能晚于系统当前日期'})
        if self.total_score is not None and not (0 <= float(self.total_score) <= 100):
            raise ValidationError({'total_score': '总分必须在 0 到 100 之间'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.student.username} - {self.measured_at} - {self.total_score}'


class TeachingInterventionPlan(models.Model):
    """基于最新有效评分和用户自评生成的个性化教学干预方案。"""

    student = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='teaching_intervention_plan',
        verbose_name='学生',
    )
    title = models.CharField(max_length=200, verbose_name='方案标题')
    summary = models.TextField(verbose_name='方案摘要')
    plan_items = models.JSONField(default=list, verbose_name='教学行动项')
    source_score_ids = models.JSONField(default=list, verbose_name='有效评分ID')
    self_assessment_snapshot = models.JSONField(default=dict, verbose_name='用户自评快照')
    input_snapshot = models.JSONField(default=dict, verbose_name='AI输入快照')
    data_age_days = models.IntegerField(null=True, blank=True, verbose_name='数据时效天数')
    validity_label = models.CharField(max_length=100, blank=True, verbose_name='时效标注')
    generated_at = models.DateTimeField(auto_now=True, verbose_name='生成时间')

    class Meta:
        verbose_name = '教学干预方案'
        verbose_name_plural = verbose_name
        ordering = ['-generated_at']

    def __str__(self):
        return f'{self.student.username} - {self.title}'
