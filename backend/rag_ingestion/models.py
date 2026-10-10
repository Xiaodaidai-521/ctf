"""Models tracking uploaded documents and their ingestion lifecycle."""

from django.conf import settings
from django.db import models


class DocumentSource(models.Model):
    """A user/admin-uploaded document ingested into the shared RAG store."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    VISIBILITY_CHOICES = [
        ('staff', 'Staff only'),
        ('internal', 'Internal (non-learner)'),
        ('learner', 'Learner visible'),
    ]

    title = models.CharField(max_length=300, verbose_name='Title')
    filename = models.CharField(max_length=400, verbose_name='Original filename')
    mime = models.CharField(max_length=120, blank=True, verbose_name='MIME type')
    byte_size = models.PositiveIntegerField(default=0, verbose_name='Byte size')
    source_hash = models.CharField(max_length=64, unique=True, verbose_name='Content hash')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    ingestion_token = models.UUIDField(null=True, blank=True, editable=False)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='internal')
    parser = models.CharField(max_length=60, blank=True, verbose_name='Parser used')
    chunk_count = models.PositiveIntegerField(default=0)
    embedded_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_rag_documents',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'RAG document source'
        verbose_name_plural = 'RAG document sources'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'visibility']),
        ]

    def __str__(self):
        return f'{self.title} ({self.status})'
