"""Permissions for legal knowledge-base APIs."""

from rest_framework.permissions import BasePermission


class IsLegalKbReader(BasePermission):
    """Allow admins and teachers to browse legal knowledge."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                request.user.is_staff
                or getattr(request.user, 'role', '') in ('admin', 'teacher')
            )
        )


class IsLegalKbAdmin(BasePermission):
    """Allow only admins to modify legal knowledge-base data."""

    @staticmethod
    def allows(user):
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and (user.is_staff or getattr(user, 'role', '') == 'admin')
        )

    def has_permission(self, request, view):
        return self.allows(request.user)
