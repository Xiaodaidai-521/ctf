# audit/admin.py
from django.contrib import admin
from .models import AIAuditLog, AuditEvent, AuditLedgerEntry
from data_security.adapters.persistence.fields import field_storage_enabled
from users.permissions import authorized_users
from django.db.models import Q


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    def get_fields(self, request, obj=None):
        excluded = self.get_exclude(request, obj) or ()
        return [name for name in super().get_fields(request, obj) if name not in excluded]

    def get_queryset(self, request):
        rows = super().get_queryset(request)
        if field_storage_enabled():
            course = request.GET.get('course', '')
            allowed = authorized_users(request.user, int(course) if course.isdecimal() else None)
            rows = rows.filter(Q(user__in=allowed) | Q(securityauditrecord__isnull=False))
        return rows

    def get_exclude(self, request, obj=None):
        return ['summary', 'detail', 'user_agent'] if field_storage_enabled() else super().get_exclude(request, obj)

    def get_list_display(self, request):
        fields = super().get_list_display(request)
        return [name for name in fields if name != 'summary'] if field_storage_enabled() else fields

    list_display = ['created_at', 'level', 'category', 'user', 'summary', 'ip_address']
    list_filter = ['level', 'category', 'created_at']
    search_fields = ['summary', 'user__username']
    readonly_fields = ['created_at', 'detail']
    ordering = ['-created_at']


@admin.register(AIAuditLog)
class AIAuditLogAdmin(admin.ModelAdmin):
    def get_fields(self, request, obj=None):
        excluded = self.get_exclude(request, obj) or ()
        return [name for name in super().get_fields(request, obj) if name not in excluded]

    def get_queryset(self, request):
        rows = super().get_queryset(request)
        if field_storage_enabled():
            course = request.GET.get('course', '')
            rows = rows.filter(security_state='sealed-v1',
                               user__in=authorized_users(request.user, int(course) if course.isdecimal() else None))
        return rows

    def get_exclude(self, request, obj=None):
        return ['user_message', 'ai_response', 'error_message'] if field_storage_enabled() else super().get_exclude(request, obj)

    list_display = ['created_at', 'provider', 'model', 'user', 'challenge', 'success', 'duration_ms']
    list_filter = ['provider', 'success', 'created_at']
    search_fields = ['user__username', 'challenge__title']
    readonly_fields = ['created_at', 'user_message', 'ai_response']
    ordering = ['-created_at']


@admin.register(AuditLedgerEntry)
class AuditLedgerEntryAdmin(admin.ModelAdmin):
    def get_fields(self, request, obj=None):
        excluded = self.get_exclude(request, obj) or ()
        return [name for name in super().get_fields(request, obj) if name not in excluded]

    def get_queryset(self, request):
        rows = super().get_queryset(request)
        if field_storage_enabled():
            course = request.GET.get('course', '')
            allowed = authorized_users(request.user, int(course) if course.isdecimal() else None)
            rows = rows.filter(Q(actor__in=allowed) | Q(securityauditrecord__isnull=False))
        return rows

    def get_exclude(self, request, obj=None):
        return ['payload'] if field_storage_enabled() else super().get_exclude(request, obj)

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
