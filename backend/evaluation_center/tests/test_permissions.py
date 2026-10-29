from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase

from evaluation_center.permissions import CanEvaluate, is_teacher


def user(role, **overrides):
    values = {'role': role, 'is_authenticated': True, 'is_active': True,
              'is_superuser': False, 'has_perm': lambda permission: False}
    return SimpleNamespace(**{**values, **overrides})


class PermissionPolicyTests(SimpleTestCase):
    def test_students_and_anonymous_are_not_teachers(self):
        self.assertFalse(is_teacher(AnonymousUser()))
        self.assertFalse(is_teacher(user('student')))

    def test_roles_not_staff_flag_determine_teaching_scope(self):
        self.assertTrue(is_teacher(user('teacher', is_staff=True)))
        self.assertTrue(is_teacher(user('admin')))
        self.assertFalse(is_teacher(user('student', is_staff=True)))
        self.assertFalse(is_teacher(user('teacher', is_active=False)))

    def test_evaluation_permission_is_separate(self):
        gate = CanEvaluate()
        for role in ('student', 'teacher'):
            self.assertFalse(gate.has_permission(SimpleNamespace(user=user(role)), None))
        self.assertTrue(gate.has_permission(SimpleNamespace(user=user('admin')), None))
        self.assertTrue(gate.has_permission(SimpleNamespace(user=user(
            'teacher', has_perm=lambda permission: permission == 'evaluation_center.manage_evaluation',
        )), None))
