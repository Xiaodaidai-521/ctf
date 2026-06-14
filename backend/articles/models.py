from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Category(models.Model):
    """文章分类"""
    name = models.CharField(max_length=50, unique=True, verbose_name='分类名称')
    description = models.TextField(blank=True, verbose_name='分类描述')
    icon = models.CharField(max_length=50, blank=True, verbose_name='图标')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    order = models.IntegerField(default=0, verbose_name='排序')

    class Meta:
        verbose_name = '文章分类'
        verbose_name_plural = verbose_name
        ordering = ['order', 'id']

    def __str__(self):
        return self.name


class Article(models.Model):
    """文章模型"""
    STATUS_CHOICES = [
        ('pending', '待审核'),
        ('approved', '已发布'),
        ('rejected', '已拒绝'),
    ]

    title = models.CharField(max_length=200, verbose_name='标题')
    content = models.TextField(verbose_name='内容（Markdown）')
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='articles',
        verbose_name='作者'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='articles',
        verbose_name='分类'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='状态'
    )
    tags = models.TextField(blank=True, verbose_name='标签（逗号分隔）')
    cover = models.ImageField(
        upload_to='articles/covers/',
        null=True,
        blank=True,
        verbose_name='封面图'
    )
    summary = models.TextField(blank=True, verbose_name='摘要')
    view_count = models.IntegerField(default=0, verbose_name='浏览次数')
    like_count = models.IntegerField(default=0, verbose_name='点赞次数')
    comment_count = models.IntegerField(default=0, verbose_name='评论次数')
    collect_count = models.IntegerField(default=0, verbose_name='收藏次数')
    is_recommend = models.BooleanField(default=False, verbose_name='是否推荐')
    is_top = models.BooleanField(default=False, verbose_name='是否置顶')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='发布时间')

    class Meta:
        verbose_name = '文章'
        verbose_name_plural = verbose_name
        ordering = ['-is_top', '-published_at', '-created_at']

    def __str__(self):
        return self.title

    @property
    def tags_list(self):
        """返回标签列表"""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
        return []


class Comment(models.Model):
    """评论模型"""
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name='文章'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name='评论者'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        verbose_name='父评论'
    )
    content = models.TextField(verbose_name='评论内容')
    like_count = models.IntegerField(default=0, verbose_name='点赞次数')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '评论'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        content_preview = self.content[:50]
        return f'{self.author.username}: {content_preview}'


class ArticleLike(models.Model):
    """文章点赞记录"""
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='likes',
        verbose_name='文章'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='article_likes',
        verbose_name='用户'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='点赞时间')

    class Meta:
        verbose_name = '文章点赞'
        verbose_name_plural = verbose_name
        unique_together = ('article', 'user')

    def __str__(self):
        return f'{self.user.username} 点赞了 {self.article.title}'


class CommentLike(models.Model):
    """评论点赞记录"""
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name='likes',
        verbose_name='评论'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='comment_likes',
        verbose_name='用户'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='点赞时间')

    class Meta:
        verbose_name = '评论点赞'
        verbose_name_plural = verbose_name
        unique_together = ('comment', 'user')

    def __str__(self):
        return f'{self.user.username} 点赞了评论'


class ArticleCollect(models.Model):
    """文章收藏记录"""
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='collects',
        verbose_name='文章'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='article_collects',
        verbose_name='用户'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='收藏时间')

    class Meta:
        verbose_name = '文章收藏'
        verbose_name_plural = verbose_name
        unique_together = ('article', 'user')

    def __str__(self):
        return f'{self.user.username} 收藏了 {self.article.title}'
