"""Permissions for legal compliance APIs."""

from rest_framework.permissions import BasePermission


class IsLegalAdmin(BasePermission):
    """Allow only administrators for sensitive legal operations."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or getattr(request.user, 'role', '') == 'admin')
        )


class IsLegalReviewer(BasePermission):
    """Allow admins and teachers to review legal analysis data."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                request.user.is_staff
                or getattr(request.user, 'role', '') in ('admin', 'teacher')
            )
        )
