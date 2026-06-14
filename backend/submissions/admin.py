from django.contrib import admin
from .models import Submission


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    """提交记录管理"""
    list_display = ['user', 'challenge', 'flag', 'is_correct', 'ip_address', 'created_at']
    list_filter = ['is_correct', 'created_at', 'challenge__category']
    search_fields = ['user__username', 'challenge__title', 'flag', 'ip_address']
    ordering = ['-created_at']

    readonly_fields = ['created_at']
