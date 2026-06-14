from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models import Sum


class CTFUser(AbstractUser):
    """教育平台用户模型"""
    ROLE_CHOICES = [
        ('student', '用户'),
        ('teacher', '教师'),
        ('admin', '管理员'),
    ]

    nickname = models.CharField(max_length=100, blank=True, verbose_name='昵称')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student', verbose_name='角色')
    score = models.IntegerField(default=0, verbose_name='总分数')
    points = models.IntegerField(default=0, verbose_name='学习积分')
    bio = models.TextField(blank=True, verbose_name='个人简介')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name='头像')
    team = models.CharField(max_length=100, blank=True, verbose_name='战队名称')
    class_name = models.CharField(max_length=100, blank=True, verbose_name='班级名称')
    student_id = models.CharField(max_length=50, blank=True, verbose_name='学号')
    enrollment_year = models.IntegerField(null=True, blank=True, verbose_name='入学年份')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '用户'
        verbose_name_plural = '用户'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    def get_solved_challenges_count(self):
        """获取已解决的题目数量"""
        return self.submission_set.filter(is_correct=True).values('challenge').distinct().count()

    def update_score(self):
        """更新总分"""
        from challenges.models import Challenge

        total_score = Challenge.objects.filter(
            submission__user=self,
            submission__is_correct=True
        ).distinct().aggregate(total=Sum('score'))['total'] or 0
        self.score = total_score
        self.save()

    @property
    def is_admin(self):
        """是否为管理员"""
        return self.role == 'admin'

    @property
    def is_teacher(self):
        """是否为教师"""
        return self.role == 'teacher'

    @property
    def is_student(self):
        """是否为用户"""
        return self.role == 'student'
