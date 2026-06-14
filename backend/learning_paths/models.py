from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType

User = get_user_model()


class LearningPath(models.Model):
    """学习路径表"""
    DIFFICULTY_CHOICES = [
        ('AP', '入门 Apprentice'),
        ('PR', '进阶 Practitioner'),
        ('EX', '专家 Expert'),
    ]

    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200, verbose_name='标题')
    slug = models.SlugField(max_length=200, unique=True, verbose_name='URL slug')
    description = models.TextField(verbose_name='描述')
    difficulty = models.CharField(max_length=2, choices=DIFFICULTY_CHOICES, verbose_name='难度')

    total_modules = models.IntegerField(default=0, verbose_name='总模块数')
    total_labs = models.IntegerField(default=0, verbose_name='总实验数')
    estimated_hours = models.FloatField(default=0, verbose_name='预计学习时长(小时)')
    cover_image = models.ImageField(
        upload_to='learning_paths/covers/',
        null=True,
        blank=True,
        verbose_name='封面图'
    )
    color = models.CharField(max_length=7, default='#1890ff', verbose_name='主题色')
    order = models.IntegerField(default=0, verbose_name='排序')
    is_published = models.BooleanField(default=False, verbose_name='是否发布')
    is_ai_generated = models.BooleanField(default=False, verbose_name='是否AI生成')
    generated_by_agent = models.CharField(max_length=50, blank=True, verbose_name='生成的Agent')
    generated_for_student = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_generated_paths',
        verbose_name='为目标用户生成'
    )
    adaptation_rules = models.JSONField(default=dict, verbose_name='适配规则')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '学习路径'
        verbose_name_plural = verbose_name
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title


class PathModule(models.Model):
    """路径模块表"""
    MODULE_TYPE_CHOICES = [
        ('intro', '介绍 Introduction'),
        ('theory', '理论 Theory'),
        ('practice', '实践 Practice'),
        ('challenge', '挑战 Challenge'),
    ]

    id = models.AutoField(primary_key=True)
    learning_path = models.ForeignKey(
        LearningPath,
        on_delete=models.CASCADE,
        related_name='modules',
        verbose_name='学习路径'
    )
    title = models.CharField(max_length=200, verbose_name='标题')
    description = models.TextField(blank=True, verbose_name='描述')
    module_type = models.CharField(max_length=20, choices=MODULE_TYPE_CHOICES, verbose_name='模块类型')
    content = models.TextField(verbose_name='内容(Markdown)')
    order = models.IntegerField(default=0, verbose_name='排序')
    parent_module = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sub_modules',
        verbose_name='父模块'
    )
    estimated_minutes = models.IntegerField(default=30, verbose_name='预计时长(分钟)')
    is_required = models.BooleanField(default=True, verbose_name='是否必修')
    requires_modules = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='required_by',
        verbose_name='前置模块'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '路径模块'
        verbose_name_plural = verbose_name
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.learning_path.title} - {self.title}"


class ModuleLab(models.Model):
    """模块-实验关联表"""
    id = models.AutoField(primary_key=True)
    module = models.ForeignKey(
        PathModule,
        on_delete=models.CASCADE,
        related_name='module_labs',
        verbose_name='模块'
    )
    lab = models.ForeignKey(
        'challenges.Challenge',
        on_delete=models.CASCADE,
        related_name='module_associations',
        verbose_name='实验'
    )
    order = models.IntegerField(default=0, verbose_name='排序')
    is_optional = models.BooleanField(default=False, verbose_name='是否可选')
    custom_hint = models.TextField(blank=True, verbose_name='自定义提示')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '模块实验关联'
        verbose_name_plural = verbose_name
        ordering = ['order', 'id']
        unique_together = ('module', 'lab')

    def __str__(self):
        return f"{self.module.title} - {self.lab.title}"


class UserPathProgress(models.Model):
    """用户路径进度表"""
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='path_progresses',
        verbose_name='用户'
    )
    learning_path = models.ForeignKey(
        LearningPath,
        on_delete=models.CASCADE,
        related_name='user_progresses',
        verbose_name='学习路径'
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='开始时间')
    last_accessed = models.DateTimeField(auto_now=True, verbose_name='最后访问时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    total_modules = models.IntegerField(default=0, verbose_name='总模块数')
    completed_modules = models.IntegerField(default=0, verbose_name='已完成模块数')
    progress_percentage = models.FloatField(default=0, verbose_name='进度百分比')
    current_module = models.ForeignKey(
        PathModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_for_users',
        verbose_name='当前模块'
    )
    current_position = models.JSONField(default=dict, verbose_name='当前位置(JSON)')

    class Meta:
        verbose_name = '用户路径进度'
        verbose_name_plural = verbose_name
        unique_together = ('user', 'learning_path')

    def __str__(self):
        return f"{self.user.username} - {self.learning_path.title}"

    def update_progress(self):
        """更新进度"""
        self.completed_modules = UserModuleProgress.objects.filter(
            user=self.user,
            module__learning_path=self.learning_path,
            status='COMPLETED'
        ).count()
        self.total_modules = PathModule.objects.filter(
            learning_path=self.learning_path,
            is_required=True
        ).count()
        if self.total_modules > 0:
            self.progress_percentage = (self.completed_modules / self.total_modules) * 100

        # 检查是否完成
        if self.completed_modules >= self.total_modules and self.progress_percentage >= 100:
            if not self.completed_at:
                from django.utils import timezone
                self.completed_at = timezone.now()

        self.save()


class UserModuleProgress(models.Model):
    """用户模块进度表"""
    STATUS_CHOICES = [
        ('LOCKED', '锁定 Locked'),
        ('AVAILABLE', '可用 Available'),
        ('IN_PROGRESS', '进行中 In Progress'),
        ('COMPLETED', '已完成 Completed'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='module_progresses',
        verbose_name='用户'
    )
    module = models.ForeignKey(
        PathModule,
        on_delete=models.CASCADE,
        related_name='user_progresses',
        verbose_name='模块'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='LOCKED', verbose_name='状态')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    last_position = models.JSONField(default=dict, verbose_name='最后位置(JSON)')
    lab_completions = models.JSONField(default=dict, verbose_name='实验完成记录(JSON)')

    class Meta:
        verbose_name = '用户模块进度'
        verbose_name_plural = verbose_name
        unique_together = ('user', 'module')

    def __str__(self):
        return f"{self.user.username} - {self.module.title}"

    def check_prerequisites(self):
        """检查前置条件"""
        required_modules = self.module.requires_modules.all()
        if not required_modules.exists():
            return True

        completed_modules = UserModuleProgress.objects.filter(
            user=self.user,
            module__in=required_modules,
            status='COMPLETED'
        ).values_list('module_id', flat=True)

        return all(req.id in completed_modules for req in required_modules)


class UserLabProgress(models.Model):
    """用户实验进度表"""
    STATUS_CHOICES = [
        ('NOT_STARTED', '未开始 Not Started'),
        ('IN_PROGRESS', '进行中 In Progress'),
        ('COMPLETED', '已完成 Completed'),
        ('FAILED', '失败 Failed'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='lab_progresses',
        verbose_name='用户'
    )
    lab = models.ForeignKey(
        'challenges.Challenge',
        on_delete=models.CASCADE,
        related_name='user_progresses',
        verbose_name='实验'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NOT_STARTED', verbose_name='状态')
    current_step = models.IntegerField(default=0, verbose_name='当前步骤')
    time_spent = models.IntegerField(default=0, verbose_name='花费时间(秒)')
    hints_used = models.PositiveIntegerField(default=0, verbose_name='使用的提示数')
    notes = models.TextField(blank=True, verbose_name='笔记')
    first_completed_at = models.DateTimeField(null=True, blank=True, verbose_name='首次完成时间')
    last_accessed = models.DateTimeField(auto_now=True, verbose_name='最后访问时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '用户实验进度'
        verbose_name_plural = verbose_name
        unique_together = ('user', 'lab')

    def __str__(self):
        return f"{self.user.username} - {self.lab.title}"


class LabAttempt(models.Model):
    """实验尝试记录表"""
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='lab_attempts',
        verbose_name='用户'
    )
    lab = models.ForeignKey(
        'challenges.Challenge',
        on_delete=models.CASCADE,
        related_name='attempts',
        verbose_name='实验'
    )
    success = models.BooleanField(default=False, verbose_name='是否成功')
    payload = models.JSONField(default=dict, verbose_name='提交内容(JSON)')
    response_summary = models.JSONField(default=dict, verbose_name='响应摘要(JSON)')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP地址')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='时间戳')

    class Meta:
        verbose_name = '实验尝试记录'
        verbose_name_plural = verbose_name
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} - {self.lab.title} - {'成功' if self.success else '失败'}"


class KnowledgeConcept(models.Model):
    """知识概念表"""
    CONCEPT_TYPE_CHOICES = [
        ('vul', '漏洞 Vulnerability'),
        ('tech', '技术 Technique'),
        ('def', '防御 Defense'),
        ('tool', '工具 Tool'),
        ('pre', '预防 Prevention'),
    ]

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200, unique=True, verbose_name='名称')
    slug = models.SlugField(max_length=200, unique=True, verbose_name='URL slug')
    description = models.TextField(verbose_name='描述')
    concept_type = models.CharField(max_length=10, choices=CONCEPT_TYPE_CHOICES, verbose_name='概念类型')
    # embedding = models.VectorField(dimensions=384, null=True, blank=True, verbose_name='向量嵌入')  # 需要安装 pgvector
    embedding = models.JSONField(null=True, blank=True, verbose_name='向量嵌入(JSON)')
    difficulty_level = models.IntegerField(default=1, verbose_name='难度级别(1-5)')
    importance = models.FloatField(default=0.5, verbose_name='重要性(0-1)')
    mitre_attack_id = models.CharField(max_length=50, blank=True, verbose_name='MITRE ATT&CK ID')
    cwe_id = models.CharField(max_length=50, blank=True, verbose_name='CWE ID')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '知识概念'
        verbose_name_plural = verbose_name
        ordering = ['name']

    def __str__(self):
        return self.name


class ConceptRelation(models.Model):
    """概念关系表"""
    RELATION_TYPE_CHOICES = [
        ('REQUIRES', '需要 Requires'),
        ('TEACHES', '教授 Teaches'),
        ('SIMILAR', '相似 Similar'),
        ('PART_OF', '部分 Part of'),
    ]

    id = models.AutoField(primary_key=True)
    from_concept = models.ForeignKey(
        KnowledgeConcept,
        on_delete=models.CASCADE,
        related_name='relations_from',
        verbose_name='源概念'
    )
    to_concept = models.ForeignKey(
        KnowledgeConcept,
        on_delete=models.CASCADE,
        related_name='relations_to',
        verbose_name='目标概念'
    )
    relation_type = models.CharField(max_length=20, choices=RELATION_TYPE_CHOICES, verbose_name='关系类型')
    strength = models.FloatField(default=1.0, verbose_name='关系强度(0-1)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '概念关系'
        verbose_name_plural = verbose_name
        unique_together = ('from_concept', 'to_concept', 'relation_type')

    def __str__(self):
        return f"{self.from_concept.name} -> {self.relation_type} -> {self.to_concept.name}"


class ConceptResource(models.Model):
    """概念-资源关联表"""
    ROLE_CHOICES = [
        ('explanation', '解释 Explanation'),
        ('example', '示例 Example'),
        ('practice', '实践 Practice'),
        ('assessment', '评估 Assessment'),
    ]

    id = models.AutoField(primary_key=True)
    concept = models.ForeignKey(
        KnowledgeConcept,
        on_delete=models.CASCADE,
        related_name='concept_resources',
        verbose_name='概念'
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name='内容类型'
    )
    object_id = models.PositiveIntegerField(verbose_name='对象ID')
    content_object = GenericForeignKey('content_type', 'object_id')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name='角色')
    weight = models.FloatField(default=1.0, verbose_name='权重')
    order = models.IntegerField(default=0, verbose_name='排序')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '概念资源关联'
        verbose_name_plural = verbose_name
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.concept.name} - {self.role}"


class UserKnowledgeState(models.Model):
    """用户知识状态表"""
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='knowledge_states',
        verbose_name='用户'
    )
    concept = models.ForeignKey(
        KnowledgeConcept,
        on_delete=models.CASCADE,
        related_name='user_states',
        verbose_name='概念'
    )
    mastery_level = models.FloatField(default=0, verbose_name='掌握程度(0-1)')
    times_viewed = models.IntegerField(default=0, verbose_name='查看次数')
    total_time_spent = models.IntegerField(default=0, verbose_name='总学习时长(秒)')
    lab_attempts = models.IntegerField(default=0, verbose_name='实验尝试次数')
    lab_successes = models.IntegerField(default=0, verbose_name='实验成功次数')
    last_reviewed = models.DateTimeField(null=True, blank=True, verbose_name='最后复习时间')
    next_review_at = models.DateTimeField(null=True, blank=True, verbose_name='下次复习时间')
    recall_probability = models.FloatField(default=0, verbose_name='回忆概率(遗忘曲线)')
    learning_velocity = models.FloatField(default=0, verbose_name='学习速度')
    struggle_indicators = models.JSONField(default=dict, verbose_name='困难指标')
    recommended_intervention = models.CharField(max_length=100, blank=True, verbose_name='推荐干预')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '用户知识状态'
        verbose_name_plural = verbose_name
        unique_together = ('user', 'concept')

    def __str__(self):
        return f"{self.user.username} - {self.concept.name} - 掌握度: {self.mastery_level:.2f}"

    def update_mastery(self, success=True, time_spent=0):
        """更新掌握程度"""
        self.times_viewed += 1
        self.total_time_spent += time_spent

        if success:
            self.lab_successes += 1
            # 成功时提升掌握度
            improvement = 0.1 * (1 - self.mastery_level)
            self.mastery_level = min(1.0, self.mastery_level + improvement)
        else:
            self.lab_attempts += 1
            # 失败时轻微降低掌握度
            self.mastery_level = max(0.0, self.mastery_level - 0.02)

        # 计算回忆概率（简化版遗忘曲线）
        from django.utils import timezone
        import math
        time_since_review = (timezone.now() - (self.last_reviewed or timezone.now())).total_seconds() / 3600
        self.recall_probability = math.exp(-time_since_review / (24 * 7))  # 7天半衰期

        self.last_reviewed = timezone.now()

        # 计算下次复习时间（间隔重复算法）
        intervals = [1, 3, 7, 14, 30, 60, 120]  # 天
        review_index = min(len(intervals) - 1, int(self.mastery_level * 10))
        self.next_review_at = timezone.now() + timezone.timedelta(days=intervals[review_index])

        self.save()


class LearningPathRecommendation(models.Model):
    """学习路径推荐表"""
    RECOMMENDATION_TYPE_CHOICES = [
        ('next_step', '下一步 Next Step'),
        ('weakness_fix', '弱点修复 Weakness Fix'),
        ('prerequisite', '前置课程 Prerequisite'),
        ('exploration', '探索 Exploration'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='path_recommendations',
        verbose_name='用户'
    )
    recommendation_type = models.CharField(max_length=20, choices=RECOMMENDATION_TYPE_CHOICES, verbose_name='推荐类型')
    path_sequence = models.JSONField(default=list, verbose_name='路径序列(JSON)')
    start_module = models.ForeignKey(
        PathModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recommendations_starting',
        verbose_name='起始模块'
    )
    start_position = models.JSONField(default=dict, verbose_name='起始位置(JSON)')
    reasoning = models.TextField(verbose_name='推荐理由')
    covered_concepts = models.ManyToManyField(
        KnowledgeConcept,
        blank=True,
        related_name='path_recommendations',
        verbose_name='覆盖的概念'
    )
    estimated_time = models.FloatField(default=0, verbose_name='预计时长(小时)')
    expected_mastery_gain = models.FloatField(default=0, verbose_name='预期掌握度提升')
    score = models.FloatField(default=0, verbose_name='推荐分数')
    is_accepted = models.BooleanField(null=True, verbose_name='是否接受')
    accepted_at = models.DateTimeField(null=True, blank=True, verbose_name='接受时间')
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name='生成时间')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='过期时间')

    class Meta:
        verbose_name = '学习路径推荐'
        verbose_name_plural = verbose_name
        ordering = ['-score', '-generated_at']

    def __str__(self):
        return f"{self.user.username} - {self.get_recommendation_type_display()}"


class ResourceRecommendation(models.Model):
    """资源推荐表"""
    REASON_TYPE_CHOICES = [
        ('weakness', '弱点 Weakness'),
        ('popular', '热门 Popular'),
        ('similar_users', '相似用户 Similar Users'),
        ('prerequisite', '前置 Prerequisite'),
        ('review', '复习 Review'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='resource_recommendations',
        verbose_name='用户'
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name='内容类型'
    )
    object_id = models.PositiveIntegerField(verbose_name='对象ID')
    content_object = GenericForeignKey('content_type', 'object_id')
    concept = models.ForeignKey(
        KnowledgeConcept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resource_recommendations',
        verbose_name='关联概念'
    )
    reason_type = models.CharField(max_length=20, choices=REASON_TYPE_CHOICES, verbose_name='原因类型')
    reason_text = models.CharField(max_length=500, verbose_name='原因文本')
    score = models.FloatField(default=0, verbose_name='推荐分数')
    impression_count = models.IntegerField(default=0, verbose_name='展示次数')
    click_count = models.IntegerField(default=0, verbose_name='点击次数')
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name='生成时间')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='过期时间')

    class Meta:
        verbose_name = '资源推荐'
        verbose_name_plural = verbose_name
        ordering = ['-score', '-generated_at']

    def __str__(self):
        return f"{self.user.username} - {self.reason_text}"


class UserLearningBehavior(models.Model):
    """用户行为日志表"""
    BEHAVIOR_TYPE_CHOICES = [
        ('view_lab', '查看实验 View Lab'),
        ('start_lab', '开始实验 Start Lab'),
        ('complete_lab', '完成实验 Complete Lab'),
        ('view_theory', '查看理论 View Theory'),
        ('complete_module', '完成模块 Complete Module'),
        ('start_path', '开始路径 Start Path'),
        ('complete_path', '完成路径 Complete Path'),
        ('view_hint', '查看提示 View Hint'),
        ('submit_flag', '提交Flag Submit Flag'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='learning_behaviors',
        verbose_name='用户'
    )
    behavior_type = models.CharField(max_length=20, choices=BEHAVIOR_TYPE_CHOICES, verbose_name='行为类型')
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='内容类型'
    )
    object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name='对象ID')
    content_object = GenericForeignKey('content_type', 'object_id')
    concepts = models.ManyToManyField(
        KnowledgeConcept,
        blank=True,
        related_name='behaviors',
        verbose_name='涉及的概念'
    )
    time_spent = models.IntegerField(default=0, verbose_name='花费时间(秒)')
    success = models.BooleanField(null=True, verbose_name='是否成功')
    score = models.FloatField(null=True, verbose_name='分数')
    session_id = models.CharField(max_length=100, blank=True, verbose_name='会话ID')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='时间戳')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP地址')

    class Meta:
        verbose_name = '用户学习行为'
        verbose_name_plural = verbose_name
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['behavior_type', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_behavior_type_display()} - {self.timestamp}"
