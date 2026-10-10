"""Models for the legal compliance knowledge base and retrieval layer."""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from pgvector.django import VectorField


class LegalDocument(models.Model):
    """Full legal document, regulation, policy, or imported knowledge source."""

    DOCUMENT_TYPE_CHOICES = [
        ('law', 'Law'),
        ('regulation', 'Regulation'),
        ('standard', 'Standard'),
        ('policy', 'Policy'),
        ('case', 'Case'),
        ('template', 'Template'),
        ('platform_content', 'Platform content'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('superseded', 'Superseded'),
        ('archived', 'Archived'),
    ]

    title = models.CharField(max_length=300, verbose_name='Title')
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES, default='law')
    jurisdiction = models.CharField(max_length=100, default='CN', verbose_name='Jurisdiction')
    issuing_authority = models.CharField(max_length=200, blank=True, verbose_name='Issuing authority')
    version_label = models.CharField(max_length=100, blank=True, verbose_name='Version label')
    source_url = models.URLField(blank=True, verbose_name='Source URL')
    source_name = models.CharField(max_length=200, blank=True, verbose_name='Source name')
    source_hash = models.CharField(max_length=64, unique=True, verbose_name='Source hash')
    full_text = models.TextField(verbose_name='Full text')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    effective_date = models.DateField(null=True, blank=True, verbose_name='Effective date')
    published_date = models.DateField(null=True, blank=True, verbose_name='Published date')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadata')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_legal_documents',
        verbose_name='Created by',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Legal document'
        verbose_name_plural = 'Legal documents'
        ordering = ['document_type', 'title']
        indexes = [
            models.Index(fields=['document_type', 'status']),
            models.Index(fields=['jurisdiction', 'effective_date']),
        ]

    def __str__(self):
        return self.title


class LegalClause(models.Model):
    """Clause-level segment for legal retrieval and citation."""

    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.CASCADE,
        related_name='clauses',
        verbose_name='Document',
    )
    clause_key = models.CharField(max_length=100, verbose_name='Clause key')
    chapter = models.CharField(max_length=200, blank=True, verbose_name='Chapter')
    article_number = models.CharField(max_length=80, blank=True, verbose_name='Article number')
    title = models.CharField(max_length=300, blank=True, verbose_name='Title')
    text = models.TextField(verbose_name='Clause text')
    text_hash = models.CharField(max_length=64, db_index=True, verbose_name='Text hash')
    order = models.PositiveIntegerField(default=0, verbose_name='Order')
    keywords = models.JSONField(default=list, blank=True, verbose_name='Keywords')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadata')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Legal clause'
        verbose_name_plural = 'Legal clauses'
        ordering = ['document', 'order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'clause_key'],
                name='unique_legal_clause_key_per_document',
            ),
        ]
        indexes = [
            models.Index(fields=['document', 'article_number']),
            models.Index(fields=['text_hash']),
        ]

    def __str__(self):
        return f'{self.document_id}:{self.clause_key}'


class LegalCase(models.Model):
    """Typical case or enforcement case used as retrieval evidence."""

    CASE_TYPE_CHOICES = [
        ('judicial', 'Judicial'),
        ('administrative', 'Administrative'),
        ('enforcement', 'Enforcement'),
        ('typical', 'Typical'),
        ('internal', 'Internal'),
    ]

    title = models.CharField(max_length=300, verbose_name='Title')
    case_type = models.CharField(max_length=30, choices=CASE_TYPE_CHOICES, default='typical')
    summary = models.TextField(blank=True, verbose_name='Summary')
    facts = models.TextField(blank=True, verbose_name='Facts')
    decision = models.TextField(blank=True, verbose_name='Decision')
    source_url = models.URLField(blank=True, verbose_name='Source URL')
    source_hash = models.CharField(max_length=64, db_index=True, verbose_name='Source hash')
    related_document = models.ForeignKey(
        LegalDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cases',
        verbose_name='Related document',
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadata')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Legal case'
        verbose_name_plural = 'Legal cases'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class LegalTemplate(models.Model):
    """Legal document or compliance report template."""

    TEMPLATE_TYPE_CHOICES = [
        ('report', 'Report'),
        ('notice', 'Notice'),
        ('consent', 'Consent'),
        ('rectification', 'Rectification'),
        ('other', 'Other'),
    ]

    title = models.CharField(max_length=200, verbose_name='Title')
    template_type = models.CharField(max_length=30, choices=TEMPLATE_TYPE_CHOICES, default='report')
    content = models.TextField(verbose_name='Content')
    variables = models.JSONField(default=list, blank=True, verbose_name='Variables')
    is_active = models.BooleanField(default=True, verbose_name='Active')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadata')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Legal template'
        verbose_name_plural = 'Legal templates'
        ordering = ['template_type', 'title']

    def __str__(self):
        return self.title


class LegalKnowledgeEmbedding(models.Model):
    """Unified vector table for legal and platform knowledge chunks."""

    SOURCE_TYPE_CHOICES = [
        ('legal_document', 'Legal document'),
        ('legal_clause', 'Legal clause'),
        ('legal_case', 'Legal case'),
        ('legal_template', 'Legal template'),
        ('challenge', 'Challenge'),
        ('article', 'Article'),
        ('resource', 'Resource'),
        ('knowledge_concept', 'Knowledge concept'),
        ('document', 'Uploaded document'),
    ]

    source_type = models.CharField(max_length=40, choices=SOURCE_TYPE_CHOICES, db_index=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    chunk_index = models.PositiveIntegerField(default=0, verbose_name='Chunk index')
    title = models.CharField(max_length=300, blank=True, verbose_name='Title')
    text = models.TextField(verbose_name='Text')
    text_hash = models.CharField(max_length=64, db_index=True, verbose_name='Text hash')
    embedding = models.JSONField(default=list, blank=True, verbose_name='Embedding')
    # Production PostgreSQL uses this field for ANN retrieval. JSON stays as a
    # portable fallback for local SQLite development and old indexed content.
    embedding_vector = VectorField(dimensions=1024, null=True, blank=True, verbose_name='Embedding vector')
    embedding_model = models.CharField(max_length=120, blank=True, verbose_name='Embedding model')
    embedding_dimension = models.PositiveIntegerField(default=0, verbose_name='Embedding dimension')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadata')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Legal knowledge embedding'
        verbose_name_plural = 'Legal knowledge embeddings'
        ordering = ['source_type', 'object_id', 'chunk_index']
        constraints = [
            models.UniqueConstraint(
                fields=['content_type', 'object_id', 'chunk_index', 'embedding_model'],
                name='unique_legal_embedding_chunk',
            ),
        ]
        indexes = [
            models.Index(fields=['source_type', 'text_hash']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f'{self.source_type}:{self.object_id}#{self.chunk_index}'


class KbIngestionJob(models.Model):
    """Track document parsing, chunking, embedding, and indexing jobs."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    job_type = models.CharField(max_length=50, default='legal_document', verbose_name='Job type')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ingestion_jobs',
        verbose_name='Document',
    )
    source_payload = models.JSONField(default=dict, blank=True, verbose_name='Source payload')
    total_chunks = models.PositiveIntegerField(default=0, verbose_name='Total chunks')
    embedded_chunks = models.PositiveIntegerField(default=0, verbose_name='Embedded chunks')
    error_message = models.TextField(blank=True, verbose_name='Error message')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_kb_ingestion_jobs',
        verbose_name='Created by',
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Started at')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Completed at')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'KB ingestion job'
        verbose_name_plural = 'KB ingestion jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.job_type} {self.status}'


class LegalRetrievalLog(models.Model):
    """Record retrieval queries and selected knowledge chunks."""

    query = models.TextField(verbose_name='Query')
    top_k = models.PositiveIntegerField(default=8, verbose_name='Top K')
    filters = models.JSONField(default=dict, blank=True, verbose_name='Filters')
    results = models.JSONField(default=list, blank=True, verbose_name='Results')
    latency_ms = models.PositiveIntegerField(default=0, verbose_name='Latency ms')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='legal_retrieval_logs',
        verbose_name='User',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')

    class Meta:
        verbose_name = 'Legal retrieval log'
        verbose_name_plural = 'Legal retrieval logs'
        ordering = ['-created_at']

    def __str__(self):
        return self.query[:80]
