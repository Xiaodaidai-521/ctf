"""Serializers for legal knowledge-base APIs."""

from rest_framework import serializers

from .models import (
    KbIngestionJob,
    LegalCase,
    LegalClause,
    LegalDocument,
    LegalKnowledgeEmbedding,
    LegalRetrievalLog,
    LegalTemplate,
)
from .services.hashing import sha256_text


class LegalDocumentSerializer(serializers.ModelSerializer):
    """Serializer for legal documents."""

    clause_count = serializers.IntegerField(source='clauses.count', read_only=True)

    class Meta:
        model = LegalDocument
        fields = [
            'id',
            'title',
            'document_type',
            'jurisdiction',
            'issuing_authority',
            'version_label',
            'source_url',
            'source_name',
            'source_hash',
            'full_text',
            'status',
            'effective_date',
            'published_date',
            'metadata',
            'created_by',
            'clause_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'source_hash', 'created_by', 'clause_count', 'created_at', 'updated_at']

    def validate(self, attrs):
        instance = self.instance
        full_text = attrs.get('full_text', getattr(instance, 'full_text', ''))
        source_url = attrs.get('source_url', getattr(instance, 'source_url', ''))
        title = attrs.get('title', getattr(instance, 'title', ''))
        if full_text:
            source_hash = sha256_text(f'{title}|{source_url}|{full_text}')
            duplicate_queryset = LegalDocument.objects.filter(source_hash=source_hash)
            if instance:
                duplicate_queryset = duplicate_queryset.exclude(pk=instance.pk)
            if duplicate_queryset.exists():
                raise serializers.ValidationError({
                    'source_hash': 'A legal document with the same title, source URL, and full text already exists.',
                })
            attrs['source_hash'] = source_hash
        return attrs


class LegalClauseSerializer(serializers.ModelSerializer):
    """Serializer for legal clauses."""

    document_title = serializers.CharField(source='document.title', read_only=True)

    class Meta:
        model = LegalClause
        fields = [
            'id',
            'document',
            'document_title',
            'clause_key',
            'chapter',
            'article_number',
            'title',
            'text',
            'text_hash',
            'order',
            'keywords',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'document_title', 'text_hash', 'created_at', 'updated_at']

    def validate(self, attrs):
        text = attrs.get('text')
        if text:
            attrs['text_hash'] = sha256_text(text)
        return attrs


class LegalCaseSerializer(serializers.ModelSerializer):
    """Serializer for legal cases."""

    class Meta:
        model = LegalCase
        fields = [
            'id',
            'title',
            'case_type',
            'summary',
            'facts',
            'decision',
            'source_url',
            'source_hash',
            'related_document',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'source_hash', 'created_at', 'updated_at']

    def validate(self, attrs):
        source_text = '|'.join([
            attrs.get('title', ''),
            attrs.get('source_url', ''),
            attrs.get('summary', ''),
            attrs.get('facts', ''),
            attrs.get('decision', ''),
        ])
        attrs['source_hash'] = sha256_text(source_text)
        return attrs


class LegalTemplateSerializer(serializers.ModelSerializer):
    """Serializer for legal templates."""

    class Meta:
        model = LegalTemplate
        fields = [
            'id',
            'title',
            'template_type',
            'content',
            'variables',
            'is_active',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LegalKnowledgeEmbeddingSerializer(serializers.ModelSerializer):
    """Serializer for embedding chunks."""

    class Meta:
        model = LegalKnowledgeEmbedding
        fields = [
            'id',
            'source_type',
            'content_type',
            'object_id',
            'chunk_index',
            'title',
            'text',
            'text_hash',
            'embedding_model',
            'embedding_dimension',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class KbIngestionJobSerializer(serializers.ModelSerializer):
    """Serializer for KB ingestion jobs."""

    document_title = serializers.CharField(source='document.title', read_only=True)

    class Meta:
        model = KbIngestionJob
        fields = [
            'id',
            'job_type',
            'status',
            'document',
            'document_title',
            'source_payload',
            'total_chunks',
            'embedded_chunks',
            'error_message',
            'created_by',
            'started_at',
            'completed_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class LegalRetrievalLogSerializer(serializers.ModelSerializer):
    """Serializer for retrieval logs."""

    class Meta:
        model = LegalRetrievalLog
        fields = [
            'id',
            'query',
            'top_k',
            'filters',
            'results',
            'latency_ms',
            'user',
            'created_at',
        ]
        read_only_fields = fields


class LegalRetrieveSerializer(serializers.Serializer):
    """Request serializer for legal retrieval."""

    query = serializers.CharField()
    top_k = serializers.IntegerField(required=False, min_value=1, max_value=20, default=8)
    filters = serializers.DictField(required=False, default=dict)
    include_raw = serializers.BooleanField(required=False, default=False)
