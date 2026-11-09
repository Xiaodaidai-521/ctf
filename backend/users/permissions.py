from rest_framework.permissions import BasePermission
from django.db.models import Q
from django.utils import timezone

from .models import CTFUser, CourseDataGrant


def authorized_users(actor, course_id=None):
    if not actor or not actor.is_authenticated or not actor.is_active:
        return CTFUser.objects.none()
    allowed = Q(pk=actor.pk)
    if actor.role in ('teacher', 'admin') and course_id is not None:
        students = CourseDataGrant.objects.filter(actor=actor, course_id=course_id,
            active=True, expires_at__gt=timezone.now()).values('student_id')
        allowed |= Q(pk__in=students)
    return CTFUser.objects.filter(allowed)


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
