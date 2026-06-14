from django.db import models
from django.conf import settings


class LearningDirection(models.Model):
    """CTF 学习方向/内容类型"""
    key = models.SlugField(max_length=50, unique=True, verbose_name='标识')
    label = models.CharField(max_length=100, verbose_name='名称')
    description = models.TextField(blank=True, verbose_name='说明')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='排序')
    is_active = models.BooleanField(default=True, verbose_name='启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '学习方向'
        verbose_name_plural = verbose_name
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.label


class StudentProfile(models.Model):
    """用户画像"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_profile',
        verbose_name='用户',
    )
    learning_goals = models.TextField(blank=True, verbose_name='学习目标')
    self_assessed_skills = models.JSONField(default=dict, verbose_name='自我评估技能')
    onboarding_completed = models.BooleanField(default=False, verbose_name='是否完成引导')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '用户画像'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} 的用户画像'


class LearningPreference(models.Model):
    """学习偏好"""
    PACE_CHOICES = [
        ('self_paced', '自主学习'),
        ('scheduled', '计划学习'),
        ('intensive', '强化学习'),
    ]

    profile = models.OneToOneField(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='preference',
        verbose_name='用户画像',
    )
    preferred_pace = models.CharField(
        max_length=20,
        choices=PACE_CHOICES,
        default='self_paced',
        verbose_name='偏好学习节奏',
    )
    preferred_modality = models.JSONField(default=list, verbose_name='偏好学习方式')
    prefers_diagrams = models.BooleanField(default=True, verbose_name='偏好图表')
    prefers_code_examples = models.BooleanField(default=True, verbose_name='偏好代码示例')
    daily_study_hours = models.FloatField(default=2, verbose_name='每日学习小时数')
    difficulty_bias = models.FloatField(default=0, verbose_name='难度偏好偏移')

    class Meta:
        verbose_name = '学习偏好'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.profile.user.username} 的学习偏好'


class LearningPersona(models.Model):
    """学习人格"""
    profile = models.OneToOneField(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='persona',
        verbose_name='用户画像',
    )
    persona_label = models.CharField(max_length=100, blank=True, verbose_name='人格标签')
    confidence_score = models.FloatField(default=0, verbose_name='置信度')
    persona_traits = models.JSONField(default=dict, verbose_name='人格特征')
    recommended_agent_roster = models.JSONField(default=list, verbose_name='推荐Agent列表')
    last_computed = models.DateTimeField(null=True, blank=True, verbose_name='上次计算时间')

    class Meta:
        verbose_name = '学习人格'
        verbose_name_plural = verbose_name

    def __str__(self):
        label = self.persona_label or '未标注'
        return f'{self.profile.user.username} 的学习人格 - {label}'
