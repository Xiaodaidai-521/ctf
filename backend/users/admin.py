from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CTFUser


@admin.register(CTFUser)
class CTFUserAdmin(UserAdmin):
    """用户管理"""
    list_display = ['username', 'nickname', 'email', 'role', 'score', 'points', 'class_name', 'created_at']
    list_filter = ['role', 'is_staff', 'created_at']
    search_fields = ['username', 'nickname', 'email', 'student_id']
    ordering = ['-created_at']

    fieldsets = UserAdmin.fieldsets + (
        ('基本信息', {'fields': ('nickname', 'role', 'bio', 'avatar', 'team', 'class_name', 'student_id')}),
        ('学习数据', {'fields': ('score', 'points')}),
    )

    readonly_fields = ['score', 'points', 'created_at', 'updated_at']
