# audit/admin.py
from django.contrib import admin
from .models import AIAuditLog, AuditEvent, AuditLedgerEntry


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'level', 'category', 'user', 'summary', 'ip_address']
    list_filter = ['level', 'category', 'created_at']
    search_fields = ['summary', 'user__username']
    readonly_fields = ['created_at', 'detail']
    ordering = ['-created_at']


@admin.register(AIAuditLog)
class AIAuditLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'provider', 'model', 'user', 'challenge', 'success', 'duration_ms']
    list_filter = ['provider', 'success', 'created_at']
    search_fields = ['user__username', 'challenge__title']
    readonly_fields = ['created_at', 'user_message', 'ai_response']
    ordering = ['-created_at']


@admin.register(AuditLedgerEntry)
class AuditLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ['id', 'created_at', 'event_category', 'object_type', 'object_id', 'actor', 'chain_version']
    list_filter = ['event_category', 'chain_version', 'created_at']
    search_fields = ['object_type', 'object_id', 'actor__username', 'current_hash', 'previous_hash']
    readonly_fields = [
        'created_at',
        'payload',
        'payload_hash',
        'previous_hash',
        'current_hash',
        'chain_version',
    ]
    ordering = ['-id']
