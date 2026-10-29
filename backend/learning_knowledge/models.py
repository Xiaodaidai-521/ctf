import uuid

from django.conf import settings
from django.db import models


class CourseGrant(models.Model):
    """Explicit membership of an existing versioned teaching catalog."""

    catalog = models.ForeignKey('learning_map.CatalogVersion', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    can_review = models.BooleanField(default=False)
    maintain_secrets = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['catalog', 'user'], name='m3_course_member')]


class Material(models.Model):
    CLASSES = [(value, value) for value in ('lesson', 'hint', 'student_analysis', 'teacher_answer', 'grading_secret')]

    material_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    catalog = models.ForeignKey('learning_map.CatalogVersion', on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    material_class = models.CharField(max_length=24, choices=CLASSES)
    hint_level = models.PositiveSmallIntegerField(null=True, blank=True)
    source_type = models.CharField(max_length=40, default='teacher_authored')
    source_object_id = models.PositiveIntegerField(null=True, blank=True)
    acl_version = models.PositiveIntegerField(default=1)
    policy_version = models.CharField(max_length=32, default='m3-policy-1')
    published_scope = models.CharField(max_length=16, default='internal')
    revoked_at = models.DateTimeField(null=True, blank=True)
    ingestion_token = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=(models.Q(material_class='hint', hint_level__gte=1, hint_level__lte=4)
                       | (~models.Q(material_class='hint') & models.Q(hint_level__isnull=True))),
            name='m3_hint_level_class',
        )]
        indexes = [models.Index(fields=['source_type', 'source_object_id'])]


class MaterialRevision(models.Model):
    """Immutable source snapshot; no vectors or second retrieval store."""

    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='revisions')
    revision = models.PositiveIntegerField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='authored_material_revisions')
    title = models.CharField(max_length=300)
    publisher = models.CharField(max_length=200)
    source_url = models.URLField(blank=True)
    source_version = models.CharField(max_length=100)
    source_date = models.DateField(null=True, blank=True)
    verified_at = models.DateField(null=True, blank=True)
    source_hash = models.CharField(max_length=64)
    source_snapshot = models.TextField()
    license_id = models.CharField(max_length=100)
    license_url = models.URLField(blank=True)
    attribution_text = models.TextField()
    reuse_scope = models.CharField(max_length=200)
    change_note = models.TextField(blank=True)
    applicability = models.TextField()
    recheck_due_at = models.DateTimeField(null=True, blank=True)
    conflict_group = models.CharField(max_length=100, blank=True)
    supersedes = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    parser_version = models.CharField(max_length=64, default='m3-paragraph-1')
    parse_status = models.CharField(max_length=16, default='pending')
    review_status = models.CharField(max_length=16, default='draft')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    ingestion_token = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['material', 'revision'], name='m3_material_revision')]


class MaterialChunk(models.Model):
    revision = models.ForeignKey(MaterialRevision, on_delete=models.PROTECT, related_name='chunks')
    index = models.PositiveIntegerField()
    start = models.PositiveIntegerField()
    end = models.PositiveIntegerField()
    chunk_hash = models.CharField(max_length=64)
    heading_path = models.JSONField(default=list)
    locator = models.JSONField(default=dict)
    embedding = models.ForeignKey('legal_kb.LegalKnowledgeEmbedding', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['revision', 'index'], name='m3_revision_chunk')]
        ordering = ['index']


class TaskMaterial(models.Model):
    task = models.ForeignKey('learning_map.TaskPackage', on_delete=models.PROTECT)
    revision = models.ForeignKey(MaterialRevision, on_delete=models.PROTECT, related_name='bindings')
    knowledge_point_ids = models.JSONField(default=list)
    capability_ids = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['task', 'revision'], name='m3_task_revision')]


class ReviewAction(models.Model):
    revision = models.ForeignKey(MaterialRevision, on_delete=models.PROTECT, related_name='actions')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=20)
    idempotency_key = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64)
    reason = models.CharField(max_length=500)
    acl_version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['revision', 'idempotency_key'], name='m3_review_request')]


class Evidence(models.Model):
    evidence_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT)
    chunk = models.ForeignKey(MaterialChunk, on_delete=models.PROTECT)
    acl_version = models.PositiveIntegerField()
    policy_version = models.CharField(max_length=32)
    purpose = models.CharField(max_length=24, default='lesson')
    decision_ref = models.UUIDField(default=uuid.uuid4)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'attempt', 'chunk', 'acl_version', 'purpose'], name='m3_evidence_issue')]


class EvidenceIssue(models.Model):
    attempt = models.ForeignKey('learning_map.TaskAttempt', on_delete=models.PROTECT)
    revision = models.ForeignKey(MaterialRevision, null=True, blank=True, on_delete=models.PROTECT)
    reason = models.CharField(max_length=24)
    ticket = models.OneToOneField('feedback_center.FeedbackTicket', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
