from django.db import models
from django.conf import settings
import json


class Category(models.Model):
    """题目分类"""
    name = models.CharField(max_length=100, unique=True, verbose_name='分类名称')
    description = models.TextField(blank=True, verbose_name='分类描述')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '题目分类'
        verbose_name_plural = '题目分类'

    def __str__(self):
        return self.name


class Challenge(models.Model):
    """CTF 题目"""
    CATEGORY_CHOICES = [
        ('web', 'Web'),
        ('crypto', 'Crypto'),
        ('misc', 'Misc'),
        ('pwn', 'Pwn'),
        ('reverse', 'Reverse'),
        ('forensics', 'Forensics'),
    ]

    DIFFICULTY_CHOICES = [
        ('easy', '简单'),
        ('medium', '中等'),
        ('hard', '困难'),
        ('expert', '专家'),
    ]

    title = models.CharField(max_length=200, verbose_name='题目名称')
    description = models.TextField(verbose_name='题目描述')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, verbose_name='分类')
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, verbose_name='难度')
    score = models.IntegerField(verbose_name='分数')
    flag = models.CharField(max_length=200, verbose_name='Flag')
    submission_mode = models.CharField(
        max_length=20, default='flag',
        choices=[('flag', 'Flag 计分'), ('practice', '自由练习')],
        verbose_name='练习模式',
    )
    hint = models.TextField(blank=True, verbose_name='提示')
    attachment = models.FileField(upload_to='attachments/', blank=True, verbose_name='附件')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    solve_count = models.IntegerField(default=0, verbose_name='解决人数')
    # Docker容器相关字段
    docker_image = models.CharField(max_length=255, blank=True, null=True, verbose_name='Docker镜像名称')
    redirect_port = models.IntegerField(blank=True, null=True, verbose_name='容器内部端口')
    redirect_type = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[('http', '子域名'), ('path', '路径路由'), ('direct', '直连')],
        verbose_name='代理类型'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = 'CTF 题目'
        verbose_name_plural = 'CTF 题目'
        ordering = ['category', 'score']

    def __str__(self):
        return f"{self.title} ({self.get_difficulty_display()}) - {self.score}分"


class ChallengeRelation(models.Model):
    """显式维护题目与题目之间的关联关系。"""

    RELATION_TYPE_CHOICES = [
        ('prerequisite', '前置题'),
        ('progression', '进阶题'),
        ('similar', '相似题'),
        ('same_topic', '同主题题'),
        ('same_attack', '同攻击面题'),
        ('same_defense', '同防御思路题'),
        ('recommended', '推荐题'),
    ]

    source_challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='outgoing_relations',
        verbose_name='源题目',
    )
    target_challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='incoming_relations',
        verbose_name='目标题目',
    )
    relation_type = models.CharField(
        max_length=30,
        choices=RELATION_TYPE_CHOICES,
        verbose_name='关系类型',
    )
    strength = models.PositiveSmallIntegerField(default=3, verbose_name='关系强度')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='排序')
    reason = models.CharField(max_length=255, blank=True, verbose_name='关系说明')
    is_bidirectional = models.BooleanField(default=False, verbose_name='是否双向')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '题目关联'
        verbose_name_plural = '题目关联'
        ordering = ['source_challenge', 'sort_order', '-strength', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['source_challenge', 'target_challenge', 'relation_type'],
                name='unique_challenge_relation_type',
            ),
            models.CheckConstraint(
                condition=~models.Q(source_challenge=models.F('target_challenge')),
                name='prevent_self_challenge_relation',
            ),
        ]
        indexes = [
            models.Index(fields=['source_challenge', 'relation_type', 'is_active']),
            models.Index(fields=['target_challenge', 'relation_type', 'is_active']),
        ]

    def __str__(self):
        return f'{self.source_challenge_id} -> {self.target_challenge_id} ({self.relation_type})'


class ChallengeArticleRelation(models.Model):
    """Explicit reading guidance from a challenge to a community article."""

    RELATION_TYPE_CHOICES = [
        ('recommended_reading', '推荐阅读'),
        ('background', '背景补充'),
        ('practice_extension', '延伸练习'),
        ('official_reference', '参考资料'),
    ]

    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='article_guidance_relations',
        verbose_name='题目',
    )
    article = models.ForeignKey(
        'articles.Article',
        on_delete=models.CASCADE,
        related_name='challenge_guidance_relations',
        verbose_name='文章',
    )
    relation_type = models.CharField(
        max_length=30,
        choices=RELATION_TYPE_CHOICES,
        default='recommended_reading',
        verbose_name='导读类型',
    )
    reason = models.CharField(max_length=255, blank=True, verbose_name='导读说明')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='排序')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '题目文章导读'
        verbose_name_plural = '题目文章导读'
        ordering = ['challenge', 'sort_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['challenge', 'article', 'relation_type'],
                name='unique_challenge_article_guidance',
            ),
        ]
        indexes = [
            models.Index(fields=['challenge', 'is_active', 'sort_order']),
            models.Index(fields=['article', 'is_active']),
        ]

    def __str__(self):
        return f'{self.challenge_id} -> article:{self.article_id} ({self.relation_type})'


class ChallengeResourceRelation(models.Model):
    """Explicit reading guidance from a challenge to a learning resource."""

    RELATION_TYPE_CHOICES = [
        ('recommended_reading', '推荐阅读'),
        ('background', '背景补充'),
        ('practice_extension', '延伸练习'),
        ('official_reference', '参考资料'),
    ]

    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='resource_guidance_relations',
        verbose_name='题目',
    )
    resource = models.ForeignKey(
        'resources.Resource',
        on_delete=models.CASCADE,
        related_name='challenge_guidance_relations',
        verbose_name='资源',
    )
    relation_type = models.CharField(
        max_length=30,
        choices=RELATION_TYPE_CHOICES,
        default='recommended_reading',
        verbose_name='导读类型',
    )
    reason = models.CharField(max_length=255, blank=True, verbose_name='导读说明')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='排序')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '题目资源导读'
        verbose_name_plural = '题目资源导读'
        ordering = ['challenge', 'sort_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['challenge', 'resource', 'relation_type'],
                name='unique_challenge_resource_guidance',
            ),
        ]
        indexes = [
            models.Index(fields=['challenge', 'is_active', 'sort_order']),
            models.Index(fields=['resource', 'is_active']),
        ]

    def __str__(self):
        return f'{self.challenge_id} -> resource:{self.resource_id} ({self.relation_type})'


class ChallengeContainer(models.Model):
    """用户题目容器记录"""
    STATUS_CHOICES = [
        ('pending', '待启动'),
        ('running', '运行中'),
        ('stopped', '已停止'),
        ('destroyed', '已销毁'),
        ('error', '错误'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='用户',
        related_name='challenge_containers'
    )
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        verbose_name='题目',
        related_name='containers'
    )
    container_id = models.CharField(max_length=100, unique=True, verbose_name='容器UUID')
    docker_container_name = models.CharField(max_length=255, verbose_name='Docker容器名称')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='状态'
    )
    port = models.IntegerField(default=0, verbose_name='映射端口')
    access_url = models.CharField(max_length=500, blank=True, verbose_name='访问URL')
    frp_config = models.TextField(blank=True, verbose_name='FRP配置')
    runtime_metadata = models.JSONField(default=dict, blank=True, verbose_name='运行资源')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='启动时间')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='过期时间')
    destroyed_at = models.DateTimeField(null=True, blank=True, verbose_name='销毁时间')

    class Meta:
        verbose_name = '题目容器'
        verbose_name_plural = '题目容器'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'challenge']),
            models.Index(fields=['status']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.challenge.title} ({self.get_status_display()})"

    @property
    def is_expired(self):
        """检查容器是否已过期"""
        if not self.expires_at:
            return False
        from django.utils import timezone
        return timezone.now() > self.expires_at

    @property
    def is_running(self):
        """检查容器是否正在运行"""
        return self.status == 'running' and not self.is_expired


class ChallengeSolution(models.Model):
    """题目解答预设"""
    ANSWER_TYPE_CHOICES = [
        ('hint', '提示词模式'),
        ('step', '步骤模式'),
        ('full', '完整答案模式'),
    ]

    challenge = models.OneToOneField(
        Challenge,
        on_delete=models.CASCADE,
        related_name='solution',
        verbose_name='对应题目'
    )
    answer_type = models.CharField(
        max_length=20,
        choices=ANSWER_TYPE_CHOICES,
        default='step',
        verbose_name='答案类型'
    )
    # 预设答案内容
    content = models.TextField(verbose_name='预设答案内容')
    # 提示词映射（JSON格式）- 只有answer_type='hint'时使用
    hint_map = models.TextField(blank=True, verbose_name='提示词映射')
    # 是否启用此预设（False时使用真AI）
    is_enabled = models.BooleanField(default=True, verbose_name='是否启用')
    # 创建时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '题目预设解答'
        verbose_name_plural = '题目预设解答'

    def __str__(self):
        return f"{self.challenge.title} - {self.get_answer_type_display()}"

    def get_hint_map(self) -> dict:
        """获取提示词映射"""
        if not self.hint_map:
            return {}
        try:
            return json.loads(self.hint_map)
        except:
            return {}

    def match_hint(self, user_message: str) -> str:
        """匹配提示词"""
        hint_map = self.get_hint_map()
        message_lower = user_message.lower()
        
        # 精确匹配
        for key, value in hint_map.items():
            if key.lower() in message_lower:
                return value
        
        # 返回默认提示
        return hint_map.get('default', self.content)
