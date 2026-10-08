from django.conf import settings
from django.db import models


class AgentRun(models.Model):
    """Persist one runtime-managed agent task."""

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    TASK_LEARNING = 'learning'
    TASK_CTF_ASSIST = 'ctf_assist'
    TASK_CONTENT = 'content'
    TASK_COMPLIANCE = 'compliance'
    TASK_GENERAL = 'general'

    TASK_TYPE_CHOICES = [
        (TASK_LEARNING, 'Learning'),
        (TASK_CTF_ASSIST, 'CTF Assist'),
        (TASK_CONTENT, 'Content'),
        (TASK_COMPLIANCE, 'Compliance'),
        (TASK_GENERAL, 'General'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_runs',
    )
    task_type = models.CharField(max_length=40, choices=TASK_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    current_step = models.CharField(max_length=100, blank=True)
    plan = models.JSONField(default=list, blank=True)
    retrieved_docs = models.JSONField(default=list, blank=True)
    used_tools = models.JSONField(default=list, blank=True)
    intermediate_result = models.JSONField(default=dict, blank=True)
    final_result = models.JSONField(default=dict, blank=True)
    verification_result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['task_type', 'status']),
        ]

    def __str__(self):
        return f'{self.task_type} run {self.id} ({self.status})'


class UserMemory(models.Model):
    """Persist long-term user memory for runtime agents."""

    MEMORY_TYPE_PREFERENCE = 'preference'
    MEMORY_TYPE_LEARNING_INSIGHT = 'learning_insight'
    MEMORY_TYPE_INTERACTION_PATTERN = 'interaction_pattern'
    MEMORY_TYPE_FACT = 'fact'
    MEMORY_TYPE_TEMPORARY = 'temporary'

    MEMORY_TYPE_CHOICES = [
        (MEMORY_TYPE_PREFERENCE, 'User Preference'),
        (MEMORY_TYPE_LEARNING_INSIGHT, 'Learning Insight'),
        (MEMORY_TYPE_INTERACTION_PATTERN, 'Interaction Pattern'),
        (MEMORY_TYPE_FACT, 'Fact'),
        (MEMORY_TYPE_TEMPORARY, 'Temporary'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_memories',
    )
    memory_type = models.CharField(max_length=40, choices=MEMORY_TYPE_CHOICES)
    memory_key = models.CharField(max_length=200, db_index=True)
    memory_value = models.JSONField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'memory_type'], name='agent_runti_user_id_e8c13c_idx'),
            models.Index(fields=['user', 'memory_key'], name='agent_runti_user_id_b9679d_idx'),
        ]
        unique_together = [['user', 'memory_type', 'memory_key']]

    def __str__(self):
        return f'{self.user.username} - {self.memory_type}:{self.memory_key}'
