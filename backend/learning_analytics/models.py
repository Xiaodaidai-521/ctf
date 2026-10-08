from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class LearningInsight(models.Model):
    INSIGHT_TYPE_CHOICES = [('strength', 'Strength'), ('weakness', 'Weakness'), ('plateau', 'Plateau'), ('acceleration', 'Acceleration'), ('recommendation', 'Recommendation')]
    SEVERITY_CHOICES = [('info', 'Info'), ('warning', 'Warning'), ('critical', 'Critical')]
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_insights', verbose_name='Student')
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPE_CHOICES, verbose_name='Insight type')
    concept = models.ForeignKey('learning_paths.KnowledgeConcept', on_delete=models.SET_NULL, null=True, blank=True, related_name='insights', verbose_name='Concept')
    title = models.CharField(max_length=200, verbose_name='Title')
    description = models.TextField(verbose_name='Description')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, verbose_name='Severity')
    actionable = models.BooleanField(default=True, verbose_name='Actionable')
    action_link = models.CharField(max_length=500, blank=True, verbose_name='Action link')
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name='Generated at')
    acknowledged_at = models.DateTimeField(null=True, blank=True, verbose_name='Acknowledged at')

    class Meta:
        verbose_name = 'Learning insight'
        verbose_name_plural = verbose_name
        ordering = ['-generated_at']
        indexes = [models.Index(fields=['student', '-generated_at']), models.Index(fields=['student', 'acknowledged_at'])]

    def __str__(self):
        return f'{self.student.username} - {self.get_insight_type_display()}: {self.title}'


class WeeklyLearningSummary(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='weekly_summaries', verbose_name='Student')
    week_start = models.DateField(verbose_name='Week start')
    total_study_minutes = models.IntegerField(default=0, verbose_name='Total study minutes')
    modules_completed = models.IntegerField(default=0, verbose_name='Completed modules')
    exercises_completed = models.IntegerField(default=0, verbose_name='Completed exercises')
    concepts_mastered = models.JSONField(default=dict, verbose_name='Mastered concepts')
    ai_interactions = models.IntegerField(default=0, verbose_name='AI interactions')
    sandbox_executions = models.IntegerField(default=0, verbose_name='Sandbox executions')
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name='Generated at')

    class Meta:
        verbose_name = 'Weekly learning summary'
        verbose_name_plural = verbose_name
        ordering = ['-week_start']
        unique_together = ('student', 'week_start')
        indexes = [models.Index(fields=['student', '-week_start'])]

    def __str__(self):
        return f'{self.student.username} - {self.week_start}'


class AdminLearningScore(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='admin_learning_scores', verbose_name='Student')
    scored_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='submitted_learning_scores', verbose_name='Scored by')
    measured_at = models.DateField(verbose_name='Measured at')
    total_score = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Total score')
    dimension_scores = models.JSONField(default=dict, blank=True, verbose_name='Dimension scores')
    tags = models.JSONField(default=list, blank=True, verbose_name='Tags')
    remark = models.TextField(blank=True, verbose_name='Remark')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Admin learning score'
        verbose_name_plural = verbose_name
        ordering = ['-measured_at', '-created_at']
        indexes = [models.Index(fields=['student', '-measured_at']), models.Index(fields=['scored_by', '-created_at'])]
        constraints = [models.CheckConstraint(condition=models.Q(total_score__gte=0) & models.Q(total_score__lte=100), name='admin_learning_score_total_0_100')]

    def clean(self):
        if self.measured_at and self.measured_at > timezone.localdate():
            raise ValidationError({'measured_at': 'Measured date cannot be in the future.'})
        if self.total_score is not None and not 0 <= float(self.total_score) <= 100:
            raise ValidationError({'total_score': 'Total score must be between 0 and 100.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.student.username} - {self.measured_at} - {self.total_score}'


class TeachingInterventionPlan(models.Model):
    student = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teaching_intervention_plan', verbose_name='Student')
    title = models.CharField(max_length=200, verbose_name='Title')
    summary = models.TextField(verbose_name='Summary')
    plan_items = models.JSONField(default=list, verbose_name='Plan items')
    source_score_ids = models.JSONField(default=list, verbose_name='Source score ids')
    self_assessment_snapshot = models.JSONField(default=dict, verbose_name='Self assessment snapshot')
    input_snapshot = models.JSONField(default=dict, verbose_name='Input snapshot')
    data_age_days = models.IntegerField(null=True, blank=True, verbose_name='Data age days')
    validity_label = models.CharField(max_length=100, blank=True, verbose_name='Validity label')
    generated_at = models.DateTimeField(auto_now=True, verbose_name='Generated at')

    class Meta:
        verbose_name = 'Teaching intervention plan'
        verbose_name_plural = verbose_name
        ordering = ['-generated_at']

    def __str__(self):
        return f'{self.student.username} - {self.title}'

class LearningBehaviorEvent(models.Model):
    EVENT_TYPES = [
        ('resource_retrieved', 'Resource retrieved'),
        ('resource_downloaded', 'Resource downloaded'),
        ('module_completed', 'Module completed'),
        ('challenge_submitted', 'Challenge submitted'),
        ('exam_submitted', 'Exam submitted'),
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learning_behavior_events',
    )
    event_type = models.CharField(max_length=32, choices=EVENT_TYPES)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['student', 'event_type', '-occurred_at']),
            models.Index(fields=['-occurred_at']),
        ]


class ResourceLearningFeedback(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='resource_learning_feedback',
    )
    resource = models.ForeignKey(
        'resources.Resource',
        on_delete=models.CASCADE,
        related_name='learning_feedback',
    )
    rating = models.PositiveSmallIntegerField()
    helpful = models.BooleanField(default=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'resource'], name='unique_resource_learning_feedback'),
            models.CheckConstraint(condition=models.Q(rating__gte=1) & models.Q(rating__lte=5), name='resource_feedback_rating_1_5'),
        ]
        indexes = [models.Index(fields=['resource', '-updated_at'])]


class LearningAdjustmentProposal(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('dismissed', 'Dismissed'),
    ]

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learning_adjustment_proposals',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_learning_adjustments',
    )
    title = models.CharField(max_length=200)
    rationale = models.TextField(blank=True)
    adjustments = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['teacher', '-created_at']),
            models.Index(fields=['student', '-created_at']),
        ]

class LearningEvent(models.Model):
    EVENT_TYPES = [
        ('content_open', 'Content open'), ('content_close', 'Content close'),
        ('video_play', 'Video play'), ('video_pause', 'Video pause'),
        ('video_progress', 'Video progress'), ('page_heartbeat', 'Page heartbeat'),
        ('page_visible', 'Page visible'), ('page_hidden', 'Page hidden'),
        ('scroll', 'Scroll'), ('click', 'Click'), ('note_create', 'Note create'),
        ('exercise_start', 'Exercise start'), ('exercise_submit', 'Exercise submit'),
        ('answer_result', 'Answer result'), ('lesson_complete', 'Lesson complete'),
        ('review_start', 'Review start'), ('login', 'Login'), ('logout', 'Logout'),
    ]

    event_id = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='analytics_events')
    course = models.ForeignKey('learning_paths.LearningPath', null=True, blank=True, on_delete=models.SET_NULL, related_name='analytics_events')
    lesson = models.ForeignKey('learning_paths.PathModule', null=True, blank=True, on_delete=models.SET_NULL, related_name='analytics_events')
    knowledge_point = models.ForeignKey('learning_paths.KnowledgeConcept', null=True, blank=True, on_delete=models.SET_NULL, related_name='analytics_events')
    event_type = models.CharField(max_length=32, choices=EVENT_TYPES)
    event_time = models.DateTimeField()
    server_time = models.DateTimeField(auto_now_add=True)
    device_id = models.CharField(max_length=128, blank=True)
    device_type = models.CharField(max_length=32, blank=True)
    client_session_id = models.CharField(max_length=128, blank=True)
    page_visible = models.BooleanField(default=True)
    duration_ms = models.PositiveIntegerField(default=0)
    progress = models.FloatField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['event_time', 'id']
        indexes = [
            models.Index(fields=['user', 'event_time']),
            models.Index(fields=['user', 'course', 'event_time']),
            models.Index(fields=['user', 'lesson', 'event_time']),
            models.Index(fields=['event_type', 'event_time']),
        ]


class LearningSession(models.Model):
    session_id = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='analytics_sessions')
    course = models.ForeignKey('learning_paths.LearningPath', null=True, blank=True, on_delete=models.SET_NULL, related_name='analytics_sessions')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    raw_duration_seconds = models.PositiveIntegerField(default=0)
    active_duration_seconds = models.PositiveIntegerField(default=0)
    effective_duration_seconds = models.PositiveIntegerField(default=0)
    idle_duration_seconds = models.PositiveIntegerField(default=0)
    video_duration_seconds = models.PositiveIntegerField(default=0)
    reading_duration_seconds = models.PositiveIntegerField(default=0)
    practice_duration_seconds = models.PositiveIntegerField(default=0)
    review_duration_seconds = models.PositiveIntegerField(default=0)
    content_count = models.PositiveIntegerField(default=0)
    interaction_count = models.PositiveIntegerField(default=0)
    session_quality_score = models.FloatField(default=0)
    abnormal_flag = models.BooleanField(default=False)
    abnormal_score = models.FloatField(default=0)
    abnormal_reason = models.CharField(max_length=255, blank=True)
    algorithm_version = models.CharField(max_length=32, default='v1')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'start_time']), models.Index(fields=['course', 'start_time'])]


class DailyLearningStat(models.Model):
    stat_date = models.DateField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_learning_stats')
    raw_learning_seconds = models.PositiveIntegerField(default=0)
    active_learning_seconds = models.PositiveIntegerField(default=0)
    effective_learning_seconds = models.PositiveIntegerField(default=0)
    video_learning_seconds = models.PositiveIntegerField(default=0)
    reading_learning_seconds = models.PositiveIntegerField(default=0)
    practice_learning_seconds = models.PositiveIntegerField(default=0)
    review_learning_seconds = models.PositiveIntegerField(default=0)
    session_count = models.PositiveIntegerField(default=0)
    completed_lesson_count = models.PositiveIntegerField(default=0)
    question_count = models.PositiveIntegerField(default=0)
    correct_question_count = models.PositiveIntegerField(default=0)
    correct_rate = models.FloatField(default=0)
    knowledge_point_count = models.PositiveIntegerField(default=0)
    focus_score = models.FloatField(default=0)
    fragmentation_rate = models.FloatField(default=0)
    effect_score = models.FloatField(default=0)
    algorithm_version = models.CharField(max_length=32, default='v1')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'stat_date', 'algorithm_version'], name='unique_daily_learning_stat')]
        indexes = [models.Index(fields=['user', 'stat_date'])]


class LearningEffectSnapshot(models.Model):
    EFFECT_LEVELS = [('excellent', 'Excellent'), ('good', 'Good'), ('developing', 'Developing'), ('at_risk', 'At risk')]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_effect_snapshots')
    analysis_start_date = models.DateField()
    analysis_end_date = models.DateField()
    time_score = models.FloatField(default=0)
    completion_score = models.FloatField(default=0)
    mastery_score = models.FloatField(default=0)
    retention_score = models.FloatField(default=0)
    consistency_score = models.FloatField(default=0)
    efficiency_score = models.FloatField(default=0)
    engagement_score = models.FloatField(default=0)
    focus_score = models.FloatField(default=0)
    total_effect_score = models.FloatField(default=0)
    effect_level = models.CharField(max_length=16, choices=EFFECT_LEVELS, default='at_risk')
    confidence_score = models.FloatField(default=0)
    sample_description = models.JSONField(default=dict, blank=True)
    algorithm_version = models.CharField(max_length=32, default='v1')
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'analysis_start_date', 'analysis_end_date', 'algorithm_version'], name='unique_learning_effect_snapshot')]
        indexes = [models.Index(fields=['user', 'analysis_end_date']), models.Index(fields=['algorithm_version'])]


class LearningRecommendation(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('accepted', 'Accepted'), ('dismissed', 'Dismissed'), ('expired', 'Expired')]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_recommendations')
    recommendation_type = models.CharField(max_length=32)
    priority = models.PositiveSmallIntegerField(default=3)
    severity = models.CharField(max_length=16, default='info')
    title = models.CharField(max_length=200)
    content = models.TextField()
    reason = models.TextField()
    evidence = models.JSONField(default=dict, blank=True)
    action_text = models.CharField(max_length=200, blank=True)
    expected_benefit = models.CharField(max_length=200, blank=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='active')
    generated_at = models.DateTimeField(auto_now_add=True)
    expire_at = models.DateTimeField(null=True, blank=True)
    algorithm_version = models.CharField(max_length=32, default='v1')

    class Meta:
        indexes = [models.Index(fields=['user', 'status', '-generated_at'])]


class LearningAuditJob(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')]
    job_id = models.CharField(max_length=64, unique=True)
    idempotency_key = models.CharField(max_length=160, unique=True)
    job_type = models.CharField(max_length=32)
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='learning_audit_jobs')
    analysis_start_time = models.DateTimeField(null=True, blank=True)
    analysis_end_time = models.DateTimeField(null=True, blank=True)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    processed_user_count = models.PositiveIntegerField(default=0)
    processed_event_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    progress = models.FloatField(default=0)
    error_message = models.TextField(blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    algorithm_version = models.CharField(max_length=32, default='v1')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
