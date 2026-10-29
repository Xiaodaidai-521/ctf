from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser
from django.db import OperationalError
from django.test import TestCase

from learning_knowledge.models import CourseGrant
from learning_knowledge.policy import Scope, authorize, can_manage
from learning_knowledge.services import search
from legal_kb.services.knowledge_retrieval_service import SafeKnowledgeRetrievalService
from .helpers import material, setup_case


class PolicyTests(TestCase):
    def setUp(self):
        setup_case(self)

    def test_t3_01_role_matrix_and_student_preview(self):
        revision = material(self)
        self.assertIsNotNone(authorize(revision.pk, self.scope))
        for user in (AnonymousUser(), None, self.other, self.teacher, self.admin):
            self.assertIsNone(authorize(revision.pk, Scope(user, self.attempt.attempt_id)))
        self.assertTrue(can_manage(self.teacher, revision.material))
        self.assertTrue(can_manage(self.admin, revision.material))
        self.assertFalse(can_manage(self.student, revision.material))

    def test_t3_01_grading_secret_needs_maintenance_duty(self):
        revision = material(self, 'grading_secret')
        self.assertFalse(can_manage(self.teacher, revision.material))
        self.assertFalse(can_manage(self.admin, revision.material))
        CourseGrant.objects.create(user=self.admin, catalog=self.task.catalog, maintain_secrets=True)
        self.assertTrue(can_manage(self.admin, revision.material))

    def test_t3_02_no_secret_title_or_body_in_search(self):
        for kind in ('student_analysis', 'teacher_answer', 'grading_secret'):
            material(self, kind, text=f'SECRET-{kind}')
        response = search(self.scope)
        self.assertEqual(response['results'], [])
        self.assertNotIn('SECRET', str(response))
        self.assertNotIn('teacher_answer', str(response))

    def test_t3_03_whitelist_intersection_cannot_be_overridden(self):
        backend = Mock()
        service = SafeKnowledgeRetrievalService(retrieval_service=backend, safe_source_types=['challenge', 'document', 'article'])
        self.assertEqual(service.safe_source_types, ('article',))
        self.assertEqual(service.retrieve(query='secret', user=self.student, task_context=self.scope,
                                         extra_filters={'source_type': ['challenge', 'document']}), [])
        backend.retrieve.assert_not_called()
        self.assertEqual(SafeKnowledgeRetrievalService(safe_source_types=[]).safe_source_types, ())

    def test_t3_05_missing_grant_and_database_error_fail_closed(self):
        revision = material(self)
        CourseGrant.objects.filter(user=self.student).delete()
        self.assertIsNone(authorize(revision.pk, self.scope))
        with patch('learning_knowledge.policy.live_attempt', side_effect=OperationalError('unavailable')):
            self.assertIsNone(authorize(revision.pk, self.scope))

    def test_t3_05_missing_source_fails_closed(self):
        revision = material(self, source_type='article', source_id=9999)
        self.assertIsNone(authorize(revision.pk, self.scope))
        self.assertEqual(search(self.scope)['results'], [])

    def test_t3_09_unreviewed_and_unknown_types_fail_closed(self):
        draft = material(self, status='draft')
        unknown = material(self, source_type='unrecognized')
        self.assertIsNone(authorize(draft.pk, self.scope))
        self.assertIsNone(authorize(unknown.pk, self.scope))

    def test_t3_09_course_task_and_catalog_are_live(self):
        revision = material(self)
        self.task.status = 'draft'
        self.task.save(update_fields=['status'])
        self.assertIsNone(authorize(revision.pk, self.scope))

    def test_t3_12_normal_search_never_delivers_hint(self):
        material(self, 'hint', level=4, text='HIGH-LEVEL-SECRET')
        self.assertEqual(search(self.scope)['results'], [])
        self.assertIsNone(authorize(1, Scope(self.student, self.attempt.attempt_id, 'hint_delivery', 4)))
