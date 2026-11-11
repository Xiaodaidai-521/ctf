"""Module assembly regressions against the production app set and root URLs."""
from types import SimpleNamespace

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import Resolver404, resolve
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView


@override_settings(ROOT_URLCONF='ctf_backend.urls')
class ModuleIntegrationTests(SimpleTestCase):
    endpoints = (
        ('post', '/api/teaching/runs/', 'teaching_agent.views.TeachingRunCreateView'),
        ('post', '/api/learning-knowledge/search/', 'learning_knowledge.views.SearchView'),
        ('get', '/api/teaching-knowledge/materials/', 'learning_knowledge.views.MaterialListView'),
        ('get', '/api/data-lab/cases/', 'data_lab.views.CasesView'),
        ('get', '/api/practical-training/mappings/', 'practical_training.views.MappingListView'),
        ('get', '/api/evaluation/students/', 'evaluation_center.views.StudentListView'),
    )

    def setUp(self):
        self.factory = APIRequestFactory()

    def test_restored_apps_are_registered(self):
        for name in ('teaching_agent', 'learning_knowledge', 'data_lab',
                     'practical_training', 'evaluation_center', 'agent_memory'):
            with self.subTest(app=name):
                self.assertTrue(apps.is_installed(name))

    def test_root_urls_reach_module_views_with_existing_authentication(self):
        for method, path, expected in self.endpoints:
            with self.subTest(path=path):
                match = resolve(path)
                view_class = match.func.view_class
                self.assertEqual(f'{view_class.__module__}.{view_class.__name__}', expected)
                self.assertEqual(view_class.authentication_classes, APIView.authentication_classes)
                self.assertEqual(settings.ROOT_URLCONF, 'ctf_backend.urls')

    def test_anonymous_requests_are_rejected_before_database_access(self):
        for method, path, expected in self.endpoints:
            with self.subTest(path=path):
                request = getattr(self.factory, method)(path, {}, format='json')
                match = resolve(path)
                response = match.func(request, **match.kwargs)
                self.assertIn(response.status_code, (401, 403))
                self.assertEqual(response.data['code'], 'authentication_required')

    def test_student_cannot_read_evaluation_student_list(self):
        path = '/api/evaluation/students/'
        request = self.factory.get(path)
        force_authenticate(request, user=SimpleNamespace(
            is_authenticated=True, is_active=True, is_superuser=False, role='student',
        ))
        response = resolve(path).func(request)
        self.assertEqual(response.status_code, 403)

    def test_teacher_needs_independent_evaluation_execution_permission(self):
        path = '/api/evaluation/runs/00000000-0000-0000-0000-000000000001/execute/'
        request = self.factory.post(path, {}, format='json')
        force_authenticate(request, user=SimpleNamespace(
            is_authenticated=True, is_active=True, is_superuser=False, role='teacher',
            has_perm=lambda permission: False,
        ))
        match = resolve(path)
        response = match.func(request, **match.kwargs)
        self.assertEqual(response.status_code, 403)

    @override_settings(EVALUATION_ISOLATED_TESTS=True, EVALUATION_TEST_ADAPTER_ENABLED=True)
    def test_test_adapter_is_not_mounted_on_production_urls(self):
        with self.assertRaises(Resolver404):
            resolve('/api/evaluation/adapter/')
