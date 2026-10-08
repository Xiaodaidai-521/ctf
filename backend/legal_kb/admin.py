"""Django admin for legal knowledge-base models."""

from django.contrib import admin

from .models import (
    KbIngestionJob,
    LegalCase,
    LegalClause,
    LegalDocument,
    LegalKnowledgeEmbedding,
    LegalRetrievalLog,
    LegalTemplate,
)


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'document_type', 'status', 'jurisdiction', 'effective_date', 'updated_at']
    list_filter = ['document_type', 'status', 'jurisdiction']
    search_fields = ['title', 'issuing_authority', 'source_url', 'source_hash']
    readonly_fields = ['source_hash', 'created_at', 'updated_at']


@admin.register(LegalClause)
class LegalClauseAdmin(admin.ModelAdmin):
    list_display = ['document', 'clause_key', 'article_number', 'order', 'updated_at']
    list_filter = ['document']
    search_fields = ['clause_key', 'article_number', 'title', 'text']
    readonly_fields = ['text_hash', 'created_at', 'updated_at']


@admin.register(LegalCase)
class LegalCaseAdmin(admin.ModelAdmin):
    list_display = ['title', 'case_type', 'related_document', 'updated_at']
    list_filter = ['case_type']
    search_fields = ['title', 'summary', 'facts', 'decision']
    readonly_fields = ['source_hash', 'created_at', 'updated_at']


@admin.register(LegalTemplate)
class LegalTemplateAdmin(admin.ModelAdmin):
    list_display = ['title', 'template_type', 'is_active', 'updated_at']
    list_filter = ['template_type', 'is_active']
    search_fields = ['title', 'content']


@admin.register(LegalKnowledgeEmbedding)
class LegalKnowledgeEmbeddingAdmin(admin.ModelAdmin):
    list_display = ['source_type', 'object_id', 'chunk_index', 'embedding_model', 'embedding_dimension', 'updated_at']
    list_filter = ['source_type', 'embedding_model']
    search_fields = ['title', 'text', 'text_hash']
    readonly_fields = ['embedding', 'metadata', 'created_at', 'updated_at']


@admin.register(KbIngestionJob)
class KbIngestionJobAdmin(admin.ModelAdmin):
    list_display = ['job_type', 'status', 'document', 'total_chunks', 'embedded_chunks', 'created_by', 'created_at']
    list_filter = ['job_type', 'status', 'created_at']
    search_fields = ['document__title', 'error_message']
    readonly_fields = ['source_payload', 'started_at', 'completed_at', 'created_at', 'updated_at']


@admin.register(LegalRetrievalLog)
class LegalRetrievalLogAdmin(admin.ModelAdmin):
    list_display = ['query', 'top_k', 'latency_ms', 'user', 'created_at']
    list_filter = ['created_at']
    search_fields = ['query']
    readonly_fields = ['filters', 'results', 'created_at']
