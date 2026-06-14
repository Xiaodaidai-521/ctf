from django.db import models


class AgentPreset(models.Model):
    """多智能体协作预设"""
    preset_id = models.SlugField(max_length=50, unique=True, verbose_name='预设标识')
    name = models.CharField(max_length=100, verbose_name='名称')
    icon = models.CharField(max_length=20, blank=True, verbose_name='图标')
    agent_ids = models.JSONField(default=list, verbose_name='智能体标识列表')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='排序')
    is_active = models.BooleanField(default=True, verbose_name='启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '智能体预设'
        verbose_name_plural = verbose_name
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.name


class ChallengeKnowledgePack(models.Model):
    """Precomputed challenge-centric knowledge pack for fast retrieval."""

    challenge = models.OneToOneField(
        'challenges.Challenge',
        on_delete=models.CASCADE,
        related_name='knowledge_pack',
        verbose_name='题目',
    )
    category_name = models.CharField(max_length=100, blank=True, verbose_name='分类名称')
    difficulty = models.CharField(max_length=20, blank=True, verbose_name='难度')
    score = models.IntegerField(default=0, verbose_name='分值')
    keywords = models.JSONField(default=list, blank=True, verbose_name='关键词')
    summary = models.TextField(blank=True, verbose_name='题目摘要')
    challenge_snapshot = models.JSONField(default=dict, blank=True, verbose_name='题目快照')
    related_challenges = models.JSONField(default=list, blank=True, verbose_name='关联题目')
    related_articles = models.JSONField(default=list, blank=True, verbose_name='关联文章')
    related_resources = models.JSONField(default=list, blank=True, verbose_name='关联资源')
    context_text = models.TextField(blank=True, verbose_name='预生成上下文')
    pack_version = models.PositiveIntegerField(default=1, verbose_name='知识包版本')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='扩展元数据')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '题目知识包'
        verbose_name_plural = verbose_name
        ordering = ['challenge_id']

    def __str__(self):
        return f'{self.challenge.title} knowledge pack'


class CategoryKnowledgePack(models.Model):
    """Precomputed category-centric knowledge pack for challenge practice."""

    category_name = models.CharField(max_length=100, unique=True, verbose_name='分类名称')
    keywords = models.JSONField(default=list, blank=True, verbose_name='分类关键词')
    featured_challenges = models.JSONField(default=list, blank=True, verbose_name='代表性题目')
    featured_articles = models.JSONField(default=list, blank=True, verbose_name='代表性文章')
    featured_resources = models.JSONField(default=list, blank=True, verbose_name='代表性资源')
    context_text = models.TextField(blank=True, verbose_name='预生成上下文')
    pack_version = models.PositiveIntegerField(default=1, verbose_name='知识包版本')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='扩展元数据')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '分类知识包'
        verbose_name_plural = verbose_name
        ordering = ['category_name']

    def __str__(self):
        return self.category_name


class AIConversation(models.Model):
    """AI对话记录"""

    user = models.ForeignKey(
        'users.CTFUser',
        on_delete=models.CASCADE,
        related_name='ai_conversations'
    )
    challenge = models.ForeignKey(
        'challenges.Challenge',
        on_delete=models.CASCADE,
        related_name='ai_conversations',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Conversation {self.id} - {self.user.username}"


class AIMessage(models.Model):
    """AI消息记录"""

    conversation = models.ForeignKey(
        AIConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(
        max_length=20,
        choices=[('user', '用户'), ('assistant', '助手')]
    )
    content = models.TextField()
    agent_id = models.CharField(max_length=50, null=True, blank=True)
    agent_name = models.CharField(max_length=100, null=True, blank=True)
    provider = models.CharField(max_length=50, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."
