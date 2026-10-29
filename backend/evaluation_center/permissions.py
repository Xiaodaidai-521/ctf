from rest_framework.permissions import BasePermission


def is_teacher(user):
    return bool(user and user.is_authenticated and user.is_active and (
        user.is_superuser or getattr(user, 'role', '') in ('teacher', 'admin')
    ))


class IsTeacher(BasePermission):
    message = '仅教师或管理员可访问教学运营记录。'

    def has_permission(self, request, view):
        return is_teacher(request.user)


class CanEvaluate(BasePermission):
    message = '需要独立的评测管理权限。'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and (
            user.is_superuser or getattr(user, 'role', '') == 'admin' or
            (getattr(user, 'role', '') == 'teacher' and
             user.has_perm('evaluation_center.manage_evaluation'))
        ))
