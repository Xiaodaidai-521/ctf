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

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or getattr(request.user, 'role', '') == 'admin')
        )
