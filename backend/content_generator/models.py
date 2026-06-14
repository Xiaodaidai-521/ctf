from django.db import models
from django.conf import settings


class GeneratedContent(models.Model):
    """AI生成内容的抽象基类"""
    CONTENT_TYPE_CHOICES = [
        ('tutorial', '教程'),
        ('quiz', '测验'),
        ('diagram', '图表'),
        ('exercise', '练习'),
    ]
    DIFFICULTY_CHOICES = [
        ('easy', '简单'),
        ('medium', '中等'),
        ('hard', '困难'),
    ]

    title = models.CharField(max_length=300, verbose_name='标题')
    content_type = models.CharField(
        max_length=20, choices=CONTENT_TYPE_CHOICES, verbose_name='内容类型'
    )
    raw_content = models.TextField(verbose_name='AI原始响应')
    rendered_assets = models.JSONField(default=dict, verbose_name='渲染资源')
    generation_params = models.JSONField(default=dict, verbose_name='生成参数')
    quality_score = models.FloatField(default=0.0, verbose_name='质量评分')
    reviewer_agent_id = models.CharField(max_length=50, blank=True, verbose_name='审核Agent ID')
    is_approved = models.BooleanField(default=False, verbose_name='是否审核通过')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created',
        verbose_name='创建者',
    )
    topic = models.ForeignKey(
        'learning_paths.KnowledgeConcept',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_related',
        verbose_name='关联知识概念',
    )
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_CHOICES, default='medium', verbose_name='难度'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class GeneratedTutorial(GeneratedContent):
    """AI生成的教程"""
    prerequisite_concepts = models.ManyToManyField(
        'learning_paths.KnowledgeConcept',
        blank=True,
        related_name='tutorials',
        verbose_name='前置概念',
    )
    estimated_minutes = models.IntegerField(default=30, verbose_name='预计学习时长(分钟)')
    sections = models.JSONField(default=list, verbose_name='章节内容')

    class Meta:
        verbose_name = '生成的教程'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.content_type:
            self.content_type = 'tutorial'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'教程: {self.title}'


class GeneratedQuiz(GeneratedContent):
    """AI生成的测验"""
    question_count = models.IntegerField(default=5, verbose_name='题目数量')
    passing_score = models.IntegerField(default=60, verbose_name='通过分数')
    questions = models.JSONField(default=list, verbose_name='题目列表')

    class Meta:
        verbose_name = '生成的测验'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.content_type:
            self.content_type = 'quiz'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'测验: {self.title}'


class GeneratedDiagram(GeneratedContent):
    """AI生成的图表"""
    DIAGRAM_TYPE_CHOICES = [
        ('flowchart', '流程图'),
        ('sequence', '时序图'),
        ('class', '类图'),
        ('architecture', '架构图'),
        ('mindmap', '思维导图'),
    ]

    diagram_type = models.CharField(
        max_length=20, choices=DIAGRAM_TYPE_CHOICES, verbose_name='图表类型'
    )
    mermaid_code = models.TextField(verbose_name='Mermaid代码')

    class Meta:
        verbose_name = '生成的图表'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.content_type:
            self.content_type = 'diagram'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'图表: {self.title}'


class GeneratedCodeExercise(GeneratedContent):
    """AI生成的代码练习"""
    language = models.CharField(max_length=50, verbose_name='编程语言')
    starter_code = models.TextField(blank=True, verbose_name='初始代码')
    test_cases = models.JSONField(default=list, verbose_name='测试用例')
    solution_code = models.TextField(blank=True, verbose_name='解答代码')
    hints = models.JSONField(default=list, verbose_name='提示列表')

    class Meta:
        verbose_name = '生成的代码练习'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.content_type:
            self.content_type = 'exercise'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'代码练习: {self.title}'
