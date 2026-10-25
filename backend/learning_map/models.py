import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from . import constants


class CatalogVersion(models.Model):
    """A frozen unit of the capability catalog.

    Stable IDs are unique inside a catalog version.  Changing the meaning of an
    ID means creating a new catalog version (and a new Capability row), never
    editing the old row in place.
    """

    version = models.CharField(max_length=64, unique=True, verbose_name='目录版本')
    label = models.CharField(max_length=200, verbose_name='版本名称')
    status = models.CharField(
        max_length=20, choices=constants.CATALOG_STATUS_CHOICES,
        default=constants.CATALOG_STATUS_CANDIDATE, verbose_name='状态',
    )
    rule_version = models.CharField(max_length=64, default=constants.RULE_VERSION, verbose_name='规则版本')
    notes = models.TextField(blank=True, verbose_name='说明')
    review_record = models.JSONField(default=dict, blank=True, verbose_name='审核记录')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='learning_map_catalogs_created', verbose_name='创建人',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    frozen_at = models.DateTimeField(null=True, blank=True, verbose_name='冻结时间')
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='发布时间')
    deprecated_at = models.DateTimeField(null=True, blank=True, verbose_name='弃用时间')

    class Meta:
        verbose_name = '能力目录版本'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.version} ({self.get_status_display()})'

    @property
    def is_published(self):
        return self.status == constants.CATALOG_STATUS_PUBLISHED


class KnowledgePoint(models.Model):
    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='knowledge_points', verbose_name='目录版本')
    stable_id = models.CharField(max_length=64, verbose_name='知识点稳定 ID')
    track = models.CharField(max_length=16, choices=constants.TRACK_CHOICES, verbose_name='主线')
    name = models.CharField(max_length=200, verbose_name='名称')
    description = models.TextField(blank=True, verbose_name='描述')
    prerequisites = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='unlocks', verbose_name='先修知识点')
    concept = models.ForeignKey(
        'learning_paths.KnowledgeConcept', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='learning_map_points', verbose_name='现有知识概念',
    )
    sort_order = models.IntegerField(default=0, verbose_name='排序')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '知识点'
        verbose_name_plural = verbose_name
        ordering = ['sort_order', 'stable_id']
        constraints = [
            models.UniqueConstraint(fields=['catalog', 'stable_id'], name='learning_map_unique_kp_per_catalog'),
        ]

    def __str__(self):
        return f'{self.stable_id} {self.name}'


class Capability(models.Model):
    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='capabilities', verbose_name='目录版本')
    stable_id = models.CharField(max_length=64, verbose_name='能力稳定 ID')
    track = models.CharField(max_length=16, choices=constants.TRACK_CHOICES, verbose_name='主线')
    title = models.CharField(max_length=200, verbose_name='能力名称')
    observable_objective = models.TextField(verbose_name='可观察目标')
    dimension = models.CharField(max_length=16, choices=constants.DIMENSION_CHOICES, verbose_name='四维归属')
    difficulty = models.PositiveSmallIntegerField(default=1, verbose_name='难度(1-5)')
    source_refs = models.JSONField(default=list, blank=True, verbose_name='来源依据')
    status = models.CharField(
        max_length=24, choices=constants.CAPABILITY_STATUS_CHOICES,
        default=constants.CAPABILITY_STATUS_TO_BUILD, verbose_name='开放状态',
    )
    course_order = models.IntegerField(default=0, verbose_name='课程顺序')
    knowledge_points = models.ManyToManyField(KnowledgePoint, blank=True, related_name='capabilities', verbose_name='关联知识点')
    prerequisites = models.ManyToManyField(
        'self', blank=True, symmetrical=False, related_name='required_by', verbose_name='先修能力',
    )
    supersedes = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='superseded_by_capabilities', verbose_name='替代的旧能力',
    )
    deprecation_note = models.TextField(blank=True, verbose_name='弃用/拆分说明')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '能力'
        verbose_name_plural = verbose_name
        ordering = ['course_order', 'stable_id']
        constraints = [
            models.UniqueConstraint(fields=['catalog', 'stable_id'], name='learning_map_unique_capability_per_catalog'),
            models.CheckConstraint(
                condition=models.Q(difficulty__gte=1) & models.Q(difficulty__lte=5),
                name='learning_map_capability_difficulty_1_5',
            ),
        ]

    def __str__(self):
        return f'{self.stable_id} {self.title}'

    @property
    def is_open(self):
        return self.status == constants.CAPABILITY_STATUS_OPEN

    @property
    def is_after_milestone_i(self):
        return self.status == constants.CAPABILITY_STATUS_AFTER_MILESTONE_I


class LegacyLabelMapping(models.Model):
    """Mapping from legacy course/challenge/profile labels to stable IDs.

    Existing rows are never deleted; a re-mapping is a new catalog version.
    Anything not confirmed by the course owner stays ``unmapped`` and is
    excluded from capability totals.
    """

    SOURCE_SYSTEM_CHOICES = [
        ('learning_path', '学习路径'),
        ('path_module', '路径模块'),
        ('challenge', '题库/实验'),
        ('knowledge_concept', '知识概念'),
        ('student_profile', '学生画像'),
        ('other', '其他'),
    ]

    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='legacy_mappings', verbose_name='目录版本')
    source_system = models.CharField(max_length=32, choices=SOURCE_SYSTEM_CHOICES, verbose_name='旧系统')
    source_label = models.CharField(max_length=255, verbose_name='旧标签')
    source_ref = models.CharField(max_length=255, blank=True, verbose_name='旧记录引用')
    capability = models.ForeignKey(Capability, null=True, blank=True, on_delete=models.SET_NULL, related_name='legacy_mappings', verbose_name='映射能力')
    knowledge_point = models.ForeignKey(KnowledgePoint, null=True, blank=True, on_delete=models.SET_NULL, related_name='legacy_mappings', verbose_name='映射知识点')
    mapping_status = models.CharField(max_length=16, choices=constants.MAPPING_STATUS_CHOICES, verbose_name='映射状态')
    note = models.TextField(blank=True, verbose_name='说明')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '旧标签映射'
        verbose_name_plural = verbose_name
        ordering = ['source_system', 'source_label']
        constraints = [
            models.UniqueConstraint(
                fields=['catalog', 'source_system', 'source_label', 'source_ref'],
                name='learning_map_unique_legacy_label',
            ),
        ]

    def __str__(self):
        return f'{self.source_system}:{self.source_label} -> {self.mapping_status}'


class WSTGMapping(models.Model):
    """Manual translation of a WSTG v4.2 scenario into a capability.

    WSTG is a testing guide, not a capability catalog.  The row is only
    advisory until a network teacher and a second reviewer sign it off.
    """

    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='wstg_mappings', verbose_name='目录版本')
    wstg_version = models.CharField(max_length=16, default='4.2', verbose_name='WSTG 版本')
    scenario_id = models.CharField(max_length=32, verbose_name='WSTG 场景编号')
    scenario_title = models.CharField(max_length=200, verbose_name='场景名称')
    capability = models.ForeignKey(Capability, null=True, blank=True, on_delete=models.SET_NULL, related_name='wstg_mappings', verbose_name='映射能力')
    prerequisite_ids = models.JSONField(default=list, blank=True, verbose_name='先修 ID')
    difficulty = models.PositiveSmallIntegerField(default=1, verbose_name='难度(1-5)')
    exercise_ref = models.CharField(max_length=255, blank=True, verbose_name='练习引用')
    acceptance_evidence = models.TextField(blank=True, verbose_name='验收证据')
    translator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='learning_map_wstg_translations', verbose_name='转译人',
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='learning_map_wstg_reviews', verbose_name='复核人',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='复核时间')
    status = models.CharField(
        max_length=16,
        choices=[('draft', '草案'), ('candidate', '候选（待审核）'), ('reviewed', '已复核'), ('rejected', '已退回')],
        default='draft', verbose_name='审核状态',
    )
    notes = models.TextField(blank=True, verbose_name='分歧与说明')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = 'WSTG 场景转译'
        verbose_name_plural = verbose_name
        ordering = ['scenario_id']
        constraints = [
            models.UniqueConstraint(fields=['catalog', 'scenario_id'], name='learning_map_unique_wstg_scenario'),
        ]

    def __str__(self):
        return f'{self.scenario_id} -> {self.capability_id}'


class DataBasisCard(models.Model):
    """Source card for the data-security track (law / standard evidence)."""

    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='data_basis_cards', verbose_name='目录版本')
    card_id = models.CharField(max_length=64, verbose_name='依据卡编号')
    capability = models.ForeignKey(Capability, null=True, blank=True, on_delete=models.SET_NULL, related_name='basis_cards', verbose_name='关联能力')
    source_title = models.CharField(max_length=255, verbose_name='来源名称')
    source_clause = models.CharField(max_length=255, blank=True, verbose_name='来源条款')
    source_version = models.CharField(max_length=128, blank=True, verbose_name='来源版本')
    source_url = models.URLField(blank=True, verbose_name='来源链接')
    applicable_facts = models.TextField(blank=True, verbose_name='适用事实')
    classification_conclusion = models.TextField(blank=True, verbose_name='分类与等级判断')
    uncertainties = models.TextField(blank=True, verbose_name='不确定项')
    protection_measures = models.TextField(blank=True, verbose_name='保护措施')
    scoring_evidence = models.TextField(blank=True, verbose_name='评分证据')
    verified_date = models.DateField(null=True, blank=True, verbose_name='核验日期')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='learning_map_basis_cards_owned', verbose_name='负责人',
    )
    change_log = models.JSONField(default=list, blank=True, verbose_name='变更记录')
    status = models.CharField(
        max_length=16,
        choices=[('draft', '草案'), ('candidate', '候选（待审核）'), ('reviewed', '已复核')],
        default='draft', verbose_name='审核状态',
    )
    notes = models.TextField(blank=True, verbose_name='说明')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '数据依据卡'
        verbose_name_plural = verbose_name
        ordering = ['card_id']
        constraints = [
            models.UniqueConstraint(fields=['catalog', 'card_id'], name='learning_map_unique_basis_card'),
        ]

    def __str__(self):
        return f'{self.card_id} {self.source_title}'


class TaskPackage(models.Model):
    """A versioned minimal task package.

    A task is only recommendable when it is frozen, its materials are not
    withdrawn, its environment is available and it does not require the
    controlled-execution milestone.  Publishing a catalog additionally checks
    that every open capability has a complete package.
    """

    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='tasks', verbose_name='目录版本')
    task_key = models.CharField(max_length=80, verbose_name='任务键')
    version = models.CharField(max_length=32, verbose_name='任务版本')
    title = models.CharField(max_length=200, verbose_name='任务名称')
    track = models.CharField(max_length=16, choices=constants.TRACK_CHOICES, verbose_name='主线')
    purpose = models.CharField(max_length=24, choices=constants.PURPOSE_CHOICES, verbose_name='任务用途')
    execution_mode = models.CharField(max_length=24, choices=constants.EXECUTION_MODE_CHOICES, verbose_name='执行方式')
    status = models.CharField(max_length=16, choices=constants.TASK_STATUS_CHOICES, default=constants.TASK_STATUS_DRAFT, verbose_name='状态')
    capabilities = models.ManyToManyField(Capability, related_name='tasks', verbose_name='目标能力')
    prerequisite_capabilities = models.ManyToManyField(
        Capability, blank=True, related_name='dependent_tasks', verbose_name='任务先修能力',
    )
    materials = models.JSONField(default=dict, verbose_name='学生材料')
    hints = models.JSONField(default=list, verbose_name='四级提示')
    student_solution_ref = models.CharField(max_length=255, blank=True, verbose_name='学生版解析引用')
    validator = models.JSONField(default=dict, verbose_name='验证器/量表')
    acceptance = models.JSONField(default=dict, verbose_name='验收要求')
    retest_task_keys = models.JSONField(default=list, blank=True, verbose_name='复测题池键')
    environment_available = models.BooleanField(default=True, verbose_name='环境可用')
    requires_milestone_i = models.BooleanField(default=False, verbose_name='需里程碑 I')
    course_order = models.IntegerField(default=0, verbose_name='课程顺序')
    challenge = models.ForeignKey(
        'challenges.Challenge', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='learning_map_tasks', verbose_name='关联题目',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '任务包'
        verbose_name_plural = verbose_name
        ordering = ['course_order', 'task_key']
        constraints = [
            models.UniqueConstraint(fields=['task_key', 'version'], name='learning_map_unique_task_version'),
        ]

    def __str__(self):
        return f'{self.task_key}@{self.version}'

    @property
    def materials_withdrawn(self):
        return bool(self.materials.get('withdrawn'))

    @property
    def is_recommendable(self):
        return (
            self.status == constants.TASK_STATUS_FROZEN
            and not self.requires_milestone_i
            and self.environment_available
            and not self.materials_withdrawn
        )

    @property
    def has_required_parts(self):
        hint_levels = {
            item.get('level') for item in (self.hints or [])
            if isinstance(item, dict)
        }
        return (
            bool(self.materials.get('student_material_refs'))
            and hint_levels.issuperset(constants.HINT_LEVELS)
            and bool(self.validator.get('type'))
            and bool(self.validator.get('version'))
            and bool(self.acceptance)
        )


class DiagnosticQuestion(models.Model):
    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='diagnostic_questions', verbose_name='目录版本')
    question_key = models.CharField(max_length=80, verbose_name='题目键')
    version = models.CharField(max_length=32, default='1.0.0', verbose_name='题目版本')
    track = models.CharField(max_length=16, choices=constants.TRACK_CHOICES, verbose_name='主线')
    capability = models.ForeignKey(Capability, on_delete=models.CASCADE, related_name='diagnostic_questions', verbose_name='目标能力')
    dimension = models.CharField(max_length=16, choices=constants.DIMENSION_CHOICES, verbose_name='维度')
    prompt = models.TextField(verbose_name='题干')
    options = models.JSONField(default=list, verbose_name='选项')
    correct_options = models.JSONField(default=list, verbose_name='正确答案（服务端）')
    points = models.PositiveSmallIntegerField(default=1, verbose_name='分值')
    status = models.CharField(
        max_length=16,
        choices=[('draft', '草案'), ('reviewed', '已复核'), ('frozen', '已冻结')],
        default='draft', verbose_name='状态',
    )
    sort_order = models.IntegerField(default=0, verbose_name='排序')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '诊断题'
        verbose_name_plural = verbose_name
        ordering = ['sort_order', 'question_key']
        constraints = [
            models.UniqueConstraint(fields=['catalog', 'question_key', 'version'], name='learning_map_unique_diagnostic_question'),
        ]

    def __str__(self):
        return f'{self.question_key} {self.capability.stable_id}'


class DiagnosticSession(models.Model):
    STATUS_CHOICES = [('in_progress', '进行中'), ('completed', '已完成')]

    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='会话 ID')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_map_diagnostic_sessions', verbose_name='学生')
    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='diagnostic_sessions', verbose_name='目录版本')
    goal_track = models.CharField(max_length=16, choices=constants.TRACK_CHOICES + [(constants.TRACK_BOTH, '双主线')], verbose_name='目标主线')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='in_progress', verbose_name='状态')
    answers = models.JSONField(default=dict, verbose_name='作答')
    result = models.JSONField(default=dict, verbose_name='结果')
    rule_version = models.CharField(max_length=64, default=constants.RULE_VERSION, verbose_name='规则版本')
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')

    class Meta:
        verbose_name = '诊断会话'
        verbose_name_plural = verbose_name
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.student_id} {self.session_id}'


class TaskAttempt(models.Model):
    """A student's attempt, used by module 6 to attach verification evidence.

    Module 1 never judges the attempt; it only records the claim and the
    evidence reference returned by the verifier.
    """

    attempt_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='尝试 ID')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_map_attempts', verbose_name='学生')
    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='attempts', verbose_name='目录版本')
    task = models.ForeignKey(TaskPackage, on_delete=models.PROTECT, related_name='attempts', verbose_name='任务包')
    task_version = models.CharField(max_length=32, verbose_name='任务版本快照')
    capability_ids = models.JSONField(default=list, verbose_name='能力 ID 快照')
    status = models.CharField(max_length=24, choices=constants.ATTEMPT_STATUS_CHOICES, default=constants.ATTEMPT_CLAIMED, verbose_name='状态')
    claimed_at = models.DateTimeField(auto_now_add=True, verbose_name='领取时间')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name='提交时间')
    submission_snapshot = models.JSONField(default=dict, blank=True, verbose_name='提交快照')
    evidence_ref = models.CharField(max_length=255, blank=True, verbose_name='证据引用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '任务尝试'
        verbose_name_plural = verbose_name
        ordering = ['-claimed_at']
        indexes = [models.Index(fields=['student', 'task', '-claimed_at'])]

    def __str__(self):
        return f'{self.attempt_id} {self.task_id}'


class VerificationFact(models.Model):
    """Verification fact handed over by module 6.

    This is the only place module 1 consumes a verification conclusion.  The
    row is idempotent by ``fact_id``; a repeated delivery returns the original
    fact, and the same ID with different content is rejected as a conflict.
    """

    fact_id = models.CharField(max_length=96, unique=True, verbose_name='事件/事实 ID')
    source = models.CharField(max_length=32, default='module6', verbose_name='来源模块')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_map_facts', verbose_name='学生')
    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='verification_facts', verbose_name='目录版本')
    capability = models.ForeignKey(Capability, on_delete=models.PROTECT, related_name='verification_facts', verbose_name='能力')
    knowledge_point = models.ForeignKey(
        KnowledgePoint, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='verification_facts', verbose_name='知识点',
    )
    task = models.ForeignKey(TaskPackage, null=True, blank=True, on_delete=models.SET_NULL, related_name='verification_facts', verbose_name='任务包')
    task_version = models.CharField(max_length=32, blank=True, verbose_name='任务版本')
    attempt_id = models.UUIDField(null=True, blank=True, verbose_name='尝试 ID')
    dimension = models.CharField(max_length=16, choices=constants.DIMENSION_CHOICES, verbose_name='维度')
    outcome = models.CharField(max_length=24, choices=constants.OUTCOME_CHOICES, verbose_name='核验结论')
    independence = models.CharField(max_length=16, choices=constants.INDEPENDENCE_CHOICES, verbose_name='独立性')
    assistance_level = models.PositiveSmallIntegerField(default=0, verbose_name='帮助层级(0-4)')
    assistance_source = models.CharField(max_length=16, choices=constants.ASSISTANCE_SOURCE_CHOICES, default=constants.ASSISTANCE_SOURCE_NONE, verbose_name='帮助来源')
    assistance_shown = models.BooleanField(default=False, verbose_name='是否实际展示帮助')
    retest_of_attempt_id = models.UUIDField(null=True, blank=True, verbose_name='复测的原尝试')
    first_attempt = models.BooleanField(default=True, verbose_name='是否首次有效尝试')
    evidence_ref = models.CharField(max_length=255, blank=True, verbose_name='证据引用')
    verifier_version = models.CharField(max_length=64, blank=True, verbose_name='验证器版本')
    occurred_at = models.DateTimeField(verbose_name='实际发生时间')
    received_at = models.DateTimeField(auto_now_add=True, verbose_name='接收时间')
    payload = models.JSONField(default=dict, blank=True, verbose_name='摘要（不含答案）')

    class Meta:
        verbose_name = '核验事实'
        verbose_name_plural = verbose_name
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['student', 'capability', '-occurred_at']),
            models.Index(fields=['catalog', 'capability']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(assistance_level__gte=0) & models.Q(assistance_level__lte=4),
                name='learning_map_assistance_level_0_4',
            ),
        ]

    def __str__(self):
        return f'{self.fact_id} {self.capability_id} {self.outcome}'


class CapabilityState(models.Model):
    """Current, explainable path state for one student / capability."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_map_states', verbose_name='学生')
    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='states', verbose_name='目录版本')
    capability = models.ForeignKey(Capability, on_delete=models.CASCADE, related_name='states', verbose_name='能力')
    state = models.CharField(max_length=24, choices=constants.STATE_CHOICES, default=constants.STATE_NEEDS_DIAGNOSIS, verbose_name='路径状态')
    diagnosis_result = models.CharField(max_length=24, choices=constants.DIAGNOSIS_RESULT_CHOICES, default=constants.DIAGNOSIS_UNKNOWN, verbose_name='诊断结果')
    reason_code = models.CharField(max_length=64, blank=True, verbose_name='原因码')
    last_fact = models.ForeignKey(VerificationFact, null=True, blank=True, on_delete=models.SET_NULL, related_name='resulting_states', verbose_name='触发事实')
    evidence_ref = models.CharField(max_length=255, blank=True, verbose_name='证据引用')
    rule_version = models.CharField(max_length=64, default=constants.RULE_VERSION, verbose_name='规则版本')
    retest_due_at = models.DateTimeField(null=True, blank=True, verbose_name='复测到期')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '能力路径状态'
        verbose_name_plural = verbose_name
        ordering = ['capability__course_order', 'capability__stable_id']
        constraints = [
            models.UniqueConstraint(fields=['student', 'catalog', 'capability'], name='learning_map_unique_state'),
        ]

    def __str__(self):
        return f'{self.student_id} {self.capability.stable_id} {self.state}'

    @property
    def state_label(self):
        return constants.STATE_LABELS.get(self.state, self.state)


class RecommendationRun(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_map_recommendations', verbose_name='学生')
    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='recommendation_runs', verbose_name='目录版本')
    goal_track = models.CharField(max_length=16, blank=True, verbose_name='目标主线')
    rule_version = models.CharField(max_length=64, verbose_name='规则版本')
    inputs_hash = models.CharField(max_length=64, verbose_name='输入摘要')
    input_snapshot = models.JSONField(default=dict, verbose_name='输入快照')
    output = models.JSONField(default=dict, verbose_name='推荐结果')
    ai_used = models.BooleanField(default=False, verbose_name='是否使用模型')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='生成时间')

    class Meta:
        verbose_name = '推荐运行'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student_id} {self.catalog_id} {self.created_at:%Y-%m-%d %H:%M}'


class PathChangeLog(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_map_change_logs', verbose_name='学生')
    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='change_logs', verbose_name='目录版本')
    capability = models.ForeignKey(Capability, null=True, blank=True, on_delete=models.SET_NULL, related_name='change_logs', verbose_name='能力')
    from_state = models.CharField(max_length=24, blank=True, verbose_name='原状态')
    to_state = models.CharField(max_length=24, blank=True, verbose_name='新状态')
    trigger_fact = models.ForeignKey(VerificationFact, null=True, blank=True, on_delete=models.SET_NULL, related_name='change_logs', verbose_name='触发事实')
    reason = models.TextField(blank=True, verbose_name='原因')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='learning_map_changes_made', verbose_name='操作人')
    rule_version = models.CharField(max_length=64, default=constants.RULE_VERSION, verbose_name='规则版本')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='时间')

    class Meta:
        verbose_name = '路径变更记录'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student_id} {self.capability_id} {self.from_state}->{self.to_state}'


class TeacherAdjustment(models.Model):
    ACTION_CHOICES = [
        ('assign_task', '指定任务'),
        ('request_retest', '安排复测'),
        ('add_note', '补充说明'),
        ('refer_review', '转交复核'),
    ]
    STATUS_CHOICES = [('recorded', '已记录'), ('applied', '已应用'), ('withdrawn', '已撤回')]

    catalog = models.ForeignKey(CatalogVersion, on_delete=models.CASCADE, related_name='teacher_adjustments', verbose_name='目录版本')
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='learning_map_adjustments_made', verbose_name='教师')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_map_adjustments', verbose_name='学生')
    capability = models.ForeignKey(Capability, null=True, blank=True, on_delete=models.SET_NULL, related_name='adjustments', verbose_name='能力')
    task = models.ForeignKey(TaskPackage, null=True, blank=True, on_delete=models.SET_NULL, related_name='adjustments', verbose_name='指定任务')
    action = models.CharField(max_length=24, choices=ACTION_CHOICES, verbose_name='动作')
    rationale = models.TextField(verbose_name='调整理由')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='recorded', verbose_name='状态')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    applied_at = models.DateTimeField(null=True, blank=True, verbose_name='应用时间')

    class Meta:
        verbose_name = '教师调整'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.teacher_id}->{self.student_id} {self.action}'


class DeliveryRegisterItem(models.Model):
    """First-phase delivery register from operation plan section 3.1.

    A ``signed_off`` row requires a real reviewer, an attachment location and a
    sign-off time.  Seed data never fills these fields.
    """

    catalog = models.ForeignKey(CatalogVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name='delivery_items', verbose_name='目录版本')
    delivery_no = models.CharField(max_length=64, unique=True, verbose_name='交付编号')
    title = models.CharField(max_length=200, verbose_name='交付项')
    required_contents = models.TextField(blank=True, verbose_name='必需内容')
    version = models.CharField(max_length=32, blank=True, verbose_name='版本')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='learning_map_delivery_authored', verbose_name='编制人',
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='learning_map_delivery_reviewed', verbose_name='复核人',
    )
    planned_hours = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, verbose_name='预计人时')
    due_date = models.DateField(null=True, blank=True, verbose_name='计划完成日')
    status = models.CharField(max_length=24, choices=constants.DELIVERY_STATUS_CHOICES, default=constants.DELIVERY_PENDING, verbose_name='状态')
    signed_off_at = models.DateTimeField(null=True, blank=True, verbose_name='审核时间')
    open_issues = models.TextField(blank=True, verbose_name='未决问题')
    attachment_path = models.CharField(max_length=500, blank=True, verbose_name='附件位置')
    notes = models.TextField(blank=True, verbose_name='说明')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '首期交付登记'
        verbose_name_plural = verbose_name
        ordering = ['delivery_no']

    def __str__(self):
        return f'{self.delivery_no} {self.get_status_display()}'

    def clean(self):
        if self.status == constants.DELIVERY_SIGNED_OFF:
            missing = []
            if not self.author_id:
                missing.append('author')
            if not self.reviewer_id:
                missing.append('reviewer')
            if not self.attachment_path:
                missing.append('attachment_path')
            if not self.signed_off_at:
                missing.append('signed_off_at')
            if missing:
                raise ValidationError({'status': f'签收缺少字段: {", ".join(missing)}'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
