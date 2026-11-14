"""Permissions for legal knowledge-base APIs."""

from rest_framework.permissions import BasePermission
from users.permissions import is_staff_or_role


def require_ingestion_actor(actor):
    """Legacy local calls may omit an actor; explicit actors need an active role."""
    if actor is not None and (
        not getattr(actor, 'is_active', False)
        or not is_staff_or_role(actor, 'teacher', 'admin')
    ):
        raise ValueError('An active staff/admin or teacher actor is required.')


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
