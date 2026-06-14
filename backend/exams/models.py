from django.db import models
from django.contrib.auth import get_user_model
import json

User = get_user_model()


class ExamLevelRule(models.Model):
    """考试等级规则"""
    grade = models.CharField('等级', max_length=10, unique=True)
    title = models.CharField('标题', max_length=100)
    description = models.TextField('描述', blank=True)
    min_score = models.PositiveIntegerField('最低分数')
    sort_order = models.PositiveIntegerField('排序', default=0)
    is_active = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'exam_level_rules'
        verbose_name = '考试等级规则'
        verbose_name_plural = '考试等级规则'
        ordering = ['-min_score', 'sort_order']

    def __str__(self):
        return f'{self.grade} - {self.title}'


class TheoryQuestion(models.Model):
    """理论题目模型"""
    QUESTION_TYPES = [
        ('single_choice', '单选题'),
        ('multiple_choice', '多选题'),
        ('true_false', '判断题'),
    ]

    DIFFICULTY_LEVELS = [
        ('easy', '简单'),
        ('medium', '中等'),
        ('hard', '困难'),
    ]

    CATEGORIES = [
        ('web', 'Web安全'),
        ('crypto', '密码学'),
        ('pwn', '二进制安全'),
        ('reverse', '逆向工程'),
        ('forensic', '取证分析'),
        ('network', '网络安全'),
        ('basic', '基础知识'),
    ]

    id = models.AutoField(primary_key=True)
    question_type = models.CharField('题目类型', max_length=20, choices=QUESTION_TYPES)
    category = models.CharField('题目分类', max_length=20, choices=CATEGORIES, default='basic')
    difficulty = models.CharField('难度等级', max_length=10, choices=DIFFICULTY_LEVELS, default='easy')
    question_text = models.TextField('题目内容')
    options = models.JSONField('选项', null=True, blank=True)  # 用于选择题和多选题
    correct_answer = models.TextField('正确答案')  # 单选/多选存选项索引，判断题存true/false
    explanation = models.TextField('解析', blank=True, default='')
    points = models.IntegerField('分值', default=10)
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'theory_questions'
        verbose_name = '理论题目'
        verbose_name_plural = '理论题目'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_question_type_display()} - {self.question_text[:50]}"


class PracticeExam(models.Model):
    """实战考试模型"""
    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('published', '已发布'),
        ('archived', '已归档'),
    ]

    id = models.AutoField(primary_key=True)
    title = models.CharField('考试标题', max_length=200)
    description = models.TextField('考试描述', blank=True, default='')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')
    duration = models.IntegerField('考试时长（分钟）', default=60)
    total_points = models.IntegerField('总分', default=100)
    easy_count = models.IntegerField('简单题数量', default=3)
    medium_count = models.IntegerField('中等题数量', default=1)
    hard_count = models.IntegerField('困难题数量', default=1)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者', related_name='created_exams')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'practice_exams'
        verbose_name = '实战考试'
        verbose_name_plural = '实战考试'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class PracticeExamQuestion(models.Model):
    """实战考试题目关联"""
    id = models.AutoField(primary_key=True)
    exam = models.ForeignKey(PracticeExam, on_delete=models.CASCADE, related_name='exam_questions')
    challenge = models.ForeignKey('challenges.Challenge', on_delete=models.CASCADE, related_name='exam_instances')
    order = models.IntegerField('题目顺序', default=0)

    class Meta:
        db_table = 'practice_exam_questions'
        verbose_name = '实战考试题目'
        verbose_name_plural = '实战考试题目'
        ordering = ['order']

    def __str__(self):
        return f"{self.exam.title} - {self.challenge.title}"


class TheoryExam(models.Model):
    """理论考试模型"""
    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('published', '已发布'),
        ('archived', '已归档'),
    ]

    id = models.AutoField(primary_key=True)
    title = models.CharField('考试标题', max_length=200)
    description = models.TextField('考试描述', blank=True, default='')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')
    duration = models.IntegerField('考试时长（分钟）', default=60)
    total_points = models.IntegerField('总分', default=100)
    random_order = models.BooleanField('随机排序', default=False)
    pass_score = models.IntegerField('及格分数', default=60)
    max_attempts = models.IntegerField('最大尝试次数', default=3)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者', related_name='created_theory_exams')
    questions = models.ManyToManyField(TheoryQuestion, through='TheoryExamQuestion', verbose_name='题目')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'theory_exams'
        verbose_name = '理论考试'
        verbose_name_plural = '理论考试'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class TheoryExamQuestion(models.Model):
    """理论考试题目关联"""
    id = models.AutoField(primary_key=True)
    exam = models.ForeignKey(TheoryExam, on_delete=models.CASCADE, related_name='exam_questions')
    question = models.ForeignKey(TheoryQuestion, on_delete=models.CASCADE, related_name='exam_instances')
    order = models.IntegerField('题目顺序', default=0)
    points = models.IntegerField('分值', default=10)

    class Meta:
        db_table = 'theory_exam_questions'
        verbose_name = '理论考试题目'
        verbose_name_plural = '理论考试题目'
        ordering = ['order']

    def __str__(self):
        return f"{self.exam.title} - {self.question.question_text[:30]}"


class ExamRecord(models.Model):
    """考试记录模型"""
    EXAM_TYPES = [
        ('theory', '理论考试'),
        ('practice', '实战训练'),
    ]

    STATUS_CHOICES = [
        ('pending', '待开始'),
        ('in_progress', '进行中'),
        ('completed', '已完成'),
        ('timeout', '超时'),
        ('abandoned', '放弃'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='考生', related_name='exam_records')
    exam_type = models.CharField('考试类型', max_length=20, choices=EXAM_TYPES)
    theory_exam = models.ForeignKey(TheoryExam, on_delete=models.CASCADE, null=True, blank=True, related_name='records')
    practice_exam = models.ForeignKey(PracticeExam, on_delete=models.CASCADE, null=True, blank=True, related_name='records')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='in_progress')
    score = models.DecimalField('得分', max_digits=5, decimal_places=2, null=True, blank=True)
    total_points = models.IntegerField('总分', default=0)
    correct_count = models.IntegerField('正确题数', default=0)
    total_questions = models.IntegerField('总题数', default=0)
    start_time = models.DateTimeField('开始时间', auto_now_add=True)
    end_time = models.DateTimeField('结束时间', null=True, blank=True)
    time_spent = models.IntegerField('用时（秒）', default=0)
    is_passed = models.BooleanField('是否通过', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'exam_records'
        verbose_name = '考试记录'
        verbose_name_plural = '考试记录'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.get_exam_type_display()} - {self.score}"


class ExamAnswer(models.Model):
    """考试作答记录"""
    id = models.AutoField(primary_key=True)
    exam_record = models.ForeignKey(ExamRecord, on_delete=models.CASCADE, related_name='answers')
    theory_question = models.ForeignKey(TheoryQuestion, on_delete=models.CASCADE, null=True, blank=True, related_name='answers')
    practice_question = models.ForeignKey(PracticeExamQuestion, on_delete=models.CASCADE, null=True, blank=True, related_name='answers')
    user_answer = models.TextField('用户答案')
    is_correct = models.BooleanField('是否正确', null=True, blank=True)
    points_earned = models.DecimalField('获得分数', max_digits=5, decimal_places=2, default=0)
    time_spent = models.IntegerField('用时（秒）', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'exam_answers'
        verbose_name = '考试作答'
        verbose_name_plural = '考试作答'
        ordering = ['id']

    def __str__(self):
        return f"{self.exam_record.user.username} - {self.user_answer}"
