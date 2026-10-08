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
    # 入门引导完成时固化，后续修改画像或重新计算都不能覆盖这份基线。
    initial_self_assessed_skills = models.JSONField(default=dict, blank=True, verbose_name='初始能力画像')
    initial_profile_captured_at = models.DateTimeField(null=True, blank=True, verbose_name='初始画像采集时间')
    onboarding_completed = models.BooleanField(default=False, verbose_name='是否完成引导')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '用户画像'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} 的用户画像'



class DynamicGrowthProfile(models.Model):
    """Persisted, server-derived learning-growth profile."""
    ANALYSIS_STATUS_CHOICES = [
        ('insufficient_data', 'Insufficient data'),
        ('ready', 'Ready for analysis'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    profile = models.OneToOneField(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='dynamic_growth',
    )
    total_learning_seconds = models.PositiveIntegerField(default=0)
    completed_question_count = models.PositiveIntegerField(default=0)
    correct_question_count = models.PositiveIntegerField(default=0)
    correct_rate = models.FloatField(default=0)
    knowledge_mastery = models.JSONField(default=dict, blank=True)
    initial_scores = models.JSONField(default=dict, blank=True)
    dynamic_scores = models.JSONField(default=dict, blank=True)
    growth_deltas = models.JSONField(default=dict, blank=True)
    growth_evidence = models.JSONField(default=dict, blank=True)
    ability_level = models.FloatField(default=0)
    risk_level = models.CharField(max_length=20, default='pending')
    recommendation_preferences = models.JSONField(default=dict, blank=True)
    analysis_status = models.CharField(
        max_length=24,
        choices=ANALYSIS_STATUS_CHOICES,
        default='insufficient_data',
    )
    analysis = models.JSONField(default=dict, blank=True)
    analysis_input_signature = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )
    last_analyzed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


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
    source_report = models.ForeignKey(
        'StudentProfileReport',
        on_delete=models.SET_NULL,
        related_name='derived_personas',
        null=True,
        blank=True,
        verbose_name='来源报表',
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


class OnboardingInterview(models.Model):
    """注册后的自然问答原始记录。"""
    STATUS_CHOICES = [
        ('in_progress', '进行中'),
        ('completed', '已完成'),
        ('failed', '分析失败'),
    ]

    profile = models.OneToOneField(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='onboarding_interview',
        verbose_name='用户画像',
    )
    answers = models.JSONField(default=dict, verbose_name='原始问答记录')
    current_question = models.PositiveSmallIntegerField(default=1, verbose_name='当前问题')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress', verbose_name='状态')
    ai_analysis = models.JSONField(default=dict, verbose_name='AI结构化分析')
    generation_provider = models.CharField(max_length=50, blank=True, verbose_name='生成模型')
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '入学画像问答'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.profile.user.username} 的入学画像问答'


class StudentProfileReport(models.Model):
    """可供学生端和管理端读取的版本化画像报表。"""
    GENERATION_STATUS_CHOICES = [
        ('completed', '生成完成'),
        ('fallback', '规则兜底'),
    ]

    profile = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='reports',
        verbose_name='用户画像',
    )
    source_interview = models.OneToOneField(
        OnboardingInterview,
        on_delete=models.PROTECT,
        related_name='report',
        null=True,
        blank=True,
        verbose_name='来源访谈',
    )
    report_type = models.CharField(max_length=20, default='initial', verbose_name='报表类型')
    version = models.PositiveIntegerField(default=1, verbose_name='版本')
    raw_interview = models.JSONField(default=list, verbose_name='原始问答快照')
    report_data = models.JSONField(default=dict, verbose_name='结构化报表')
    summary = models.TextField(blank=True, verbose_name='画像摘要')
    generation_provider = models.CharField(max_length=50, blank=True, verbose_name='生成模型')
    generation_status = models.CharField(
        max_length=20,
        choices=GENERATION_STATUS_CHOICES,
        default='completed',
        verbose_name='生成状态',
    )
    input_signature = models.CharField(max_length=64, blank=True, db_index=True, verbose_name='输入签名')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='生成时间')

    class Meta:
        verbose_name = '学生画像报表'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['profile', 'report_type', 'version'], name='unique_profile_report_version'),
        ]

    def __str__(self):
        return f'{self.profile.user.username} {self.report_type} v{self.version}'
