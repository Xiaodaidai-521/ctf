# audit/admin.py
from django.contrib import admin
from .models import AuditEvent, AIAuditLog


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
