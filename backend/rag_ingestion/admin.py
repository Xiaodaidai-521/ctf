from django.contrib import admin

from .models import DocumentSource


@admin.register(DocumentSource)
class DocumentSourceAdmin(admin.ModelAdmin):
    list_display = ['title', 'filename', 'status', 'visibility', 'parser',
                    'chunk_count', 'embedded_count', 'updated_at']
    list_filter = ['status', 'visibility', 'parser']
    search_fields = ['title', 'filename', 'source_hash']
    readonly_fields = ['source_hash', 'metadata', 'created_at', 'updated_at']
