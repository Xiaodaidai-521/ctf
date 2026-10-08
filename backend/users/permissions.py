from rest_framework.permissions import BasePermission


def is_staff_or_role(user, *roles):
    return bool(
        user
        and user.is_authenticated
        and (user.is_staff or getattr(user, 'role', None) in roles)
    )


class IsTeacherOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_staff_or_role(request.user, 'teacher', 'admin')


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return is_staff_or_role(request.user, 'admin')
