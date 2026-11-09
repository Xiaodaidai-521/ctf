from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager
from data_security.adapters.persistence.fields import ProtectedModel, ProtectedQuerySet
from django.db.models import Sum


class CTFUserManager(UserManager.from_queryset(ProtectedQuerySet)):
    pass


class CTFUser(ProtectedModel, AbstractUser):
    """教育平台用户模型"""
    encrypted_fields = ('email',)
    objects = CTFUserManager()
    email_index = models.CharField(max_length=100, blank=True, default='', db_index=True, editable=False)
    email_index_previous = models.CharField(max_length=100, blank=True, default='', db_index=True, editable=False)
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
    is_course_owner = models.BooleanField(
        default=False,
        verbose_name='课程负责人',
        help_text='可维护能力目录、交付登记与发布前审核材料；管理员始终具备此权限。',
    )
    class_name = models.CharField(max_length=100, blank=True, verbose_name='班级名称')
    student_id = models.CharField(max_length=50, blank=True, verbose_name='学号')
    enrollment_year = models.IntegerField(null=True, blank=True, verbose_name='入学年份')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '用户'
        verbose_name_plural = '用户'
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(
            condition=models.Q(security_state='legacy-v0') | models.Q(email=''),
            name='user_sealed_email_no_plaintext')]

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
    def can_manage_catalog(self):
        """目录审核权限：管理员或显式标记的课程负责人。"""
        return bool(self.role == 'admin' or (self.role == 'teacher' and self.is_course_owner))

    @property
    def is_student(self):
        """是否为用户"""
        return self.role == 'student'


class CourseDataGrant(models.Model):
    """Explicit course-scoped data access, independent of roles and learning progress."""
    actor = models.ForeignKey(CTFUser, on_delete=models.CASCADE, related_name='course_data_grants')
    student = models.ForeignKey(CTFUser, on_delete=models.CASCADE, related_name='data_access_grants')
    course = models.ForeignKey('learning_paths.LearningPath', on_delete=models.CASCADE)
    granted_by = models.ForeignKey(CTFUser, on_delete=models.PROTECT, related_name='issued_data_grants')
    expires_at = models.DateTimeField()
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('actor', 'student', 'course'), name='unique_course_data_grant')]


