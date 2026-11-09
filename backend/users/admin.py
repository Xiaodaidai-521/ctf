from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CTFUser
from .permissions import authorized_users
from data_security.adapters.persistence.fields import field_storage_enabled


@admin.register(CTFUser)
class CTFUserAdmin(UserAdmin):
    """用户管理"""
    def get_queryset(self, request):
        rows = super().get_queryset(request)
        if field_storage_enabled():
            course = request.GET.get('course', '')
            rows = rows.filter(pk__in=authorized_users(request.user, int(course) if course.isdecimal() else None),
                               security_state='sealed-v1')
        return rows

    list_display = ['username', 'nickname', 'email', 'role', 'score', 'points', 'class_name', 'created_at']
    list_filter = ['role', 'is_staff', 'created_at']
    search_fields = ['username', 'nickname', 'student_id']
    ordering = ['-created_at']

    fieldsets = UserAdmin.fieldsets + (
        ('基本信息', {'fields': ('nickname', 'role', 'bio', 'avatar', 'team', 'class_name', 'student_id')}),
        ('学习数据', {'fields': ('score', 'points')}),
    )

    readonly_fields = ['score', 'points', 'created_at', 'updated_at']

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return (*fields, 'email') if obj and obj.security_state != 'legacy-v0' else fields
