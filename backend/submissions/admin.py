from django.contrib import admin
from .models import Submission
from users.permissions import authorized_users
from data_security.adapters.persistence.fields import field_storage_enabled


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    """提交记录管理"""
    def get_queryset(self, request):
        rows = super().get_queryset(request)
        if field_storage_enabled():
            course = request.GET.get('course', '')
            rows = rows.filter(user__in=authorized_users(request.user, int(course) if course.isdecimal() else None),
                               security_state='sealed-v1')
        return rows

    list_display = ['user', 'challenge', 'flag', 'is_correct', 'ip_address', 'created_at']
    list_filter = ['is_correct', 'created_at', 'challenge__category']
    search_fields = ['user__username', 'challenge__title', 'ip_address']

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        return fields + ['flag'] if obj and obj.security_state != 'legacy-v0' else fields
    ordering = ['-created_at']

    readonly_fields = ['created_at']
