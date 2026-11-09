"""Legal owner fields and exits on the isolated PostgreSQL adapter."""
from datetime import timedelta
from importlib import import_module
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence.fields import bind_field_storage
from data_security.tests.phase4_fixtures import field_configuration
from learning_paths.models import LearningPath
from users.models import CTFUser, CourseDataGrant

from .admin import LegalAnalysisTaskAdmin, LegalReportAdmin
from .models import (ComplianceAgentRun, LegalAnalysisTask, LegalEvidence,
                     LegalFactSnapshot, LegalReport)
from .serializers import (LegalAnalysisTaskSerializer, LegalEvidenceSerializer,
                          LegalFactSnapshotSerializer, LegalReportSerializer)
from .services.compliance_orchestrator import ComplianceOrchestrator
from .services.data_access import authorized_legal_objects
from .services.fact_renderer import render_for_analysis
from .services.legal_retriever import LegalRetriever
from .services.report_generator import ReportGenerator
from .views import LegalAnalysisTaskViewSet, LegalEvidenceViewSet


class LegalFieldStorageTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        fixture = field_configuration()
        path, config, refs, binding = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.components = assemble(config_path=path)
        bind_field_storage(self.components['fields'])
        self.addCleanup(bind_field_storage, None)
        self.actor = CTFUser.objects.create_user(username='legal-field-admin', role='admin')

    def test_one_hundred_values_each_and_raw_database_copy(self):
        originals = []
        for number in range(100):
            email = f'Legal{number}@example.invalid'
            original = f'Legal synthetic {number}: {email} 192.0.2.42 4111111111111111'
            task = LegalAnalysisTask.objects.create(title=original, input_text=original,
                result_summary=original, metadata={'note': original, 'count': number}, created_by=self.actor)
            report = LegalReport.objects.create(task=task, title=original, summary=original,
                content=original, metadata={'note': original, 'count': number}, generated_by=self.actor)
            snapshot = LegalFactSnapshot.objects.create(source_kind='hybrid',
                scope={'subject_user_id': self.actor.pk}, automated_facts={'note': original, 'count': number},
                manual_notes=original, warnings=[original], evidence_refs=[{'audit_event_id': number}],
                preview_hash='1' * 64, snapshot_hash='2' * 64, confirmed_by=self.actor)
            evidence = LegalEvidence.objects.create(task=task, evidence_type='manual', title=original,
                excerpt=original, metadata={'note': original, 'count': number})
            run = ComplianceAgentRun.objects.create(task=task,
                input_payload={'note': original, 'count': number}, output_payload={'note': original})
            for instance, field in ((task, 'input_text'), (report, 'content'), (snapshot, 'manual_notes')):
                instance.refresh_from_db()
                self.assertEqual(getattr(instance, field), '')
                self.assertEqual(instance.read_protected(field), original)
            self.assertEqual(snapshot.evidence_refs, [{'audit_event_id': number}])
            self.assertEqual(task.metadata['count'], number)
            self.assertNotIn(email, json.dumps(evidence.metadata))
            self.assertNotIn(email, json.dumps(run.input_payload))
            originals.append(email)
        with connection.cursor() as cursor:
            for table in ('legal_legalanalysistask', 'legal_legalreport', 'legal_legalfactsnapshot',
                          'legal_legalevidence', 'legal_complianceagentrun'):
                cursor.execute(f'SELECT row_to_json(item) FROM {table} AS item')
                copy = json.dumps(cursor.fetchall())
                self.assertTrue(all(value not in copy for value in originals), table)

    def test_copy_chain_protects_before_truncating_and_report_keeps_explicit_input(self):
        original = 'Notes@example.invalid'
        snapshot = LegalFactSnapshot.objects.create(source_kind='hybrid', scope={},
            automated_facts={}, manual_notes=original, preview_hash='1' * 64,
            snapshot_hash='2' * 64, confirmed_by=self.actor)
        self.assertEqual(snapshot.read_protected('manual_notes'), original)
        self.assertNotIn(original, render_for_analysis(snapshot))
        task = LegalAnalysisTask.objects.create(title='Synthetic task', input_text=original,
                                               created_by=self.actor)
        self.assertNotIn(original, LegalRetriever._build_query(None, task))
        rendered = ReportGenerator()._render_markdown(task=task, findings=[], evidence_items=[])
        self.assertIn(original, rendered)
        report = LegalReport.objects.create(task=task, title='Synthetic report', content=rendered,
                                           generated_by=self.actor)
        self.assertIn(original, report.read_protected('content'))
        orchestrator = ComplianceOrchestrator()
        evidence = orchestrator._create_evidence_items(task=task, finding=None, retrieved=[{
            'text': 'x' * 1990 + ' ' + original,
            'title': 'Synthetic reference',
        }])[0]
        self.assertTrue(evidence.excerpt.startswith('x' * 1990 + ' '))
        self.assertLessEqual(len(evidence.excerpt), 2000)
        self.assertNotIn('Notes@', evidence.excerpt)
        for serializer, instance, field in (
            (LegalAnalysisTaskSerializer, task, 'input_text'),
            (LegalReportSerializer, report, 'content'),
            (LegalFactSnapshotSerializer, snapshot, 'manual_notes'),
        ):
            payload = serializer(instance).data
            self.assertEqual(payload[field], '[REDACTED]')
            self.assertNotIn(original, json.dumps(payload))
            self.assertNotIn('security_envelopes', payload)

    def test_orchestrator_passes_explicit_input_without_owner_model_coupling(self):
        from data_security.adapters.django.content import bind_content_protection

        bind_content_protection(self.components['protect_text'])
        self.addCleanup(bind_content_protection, None)
        original = 'Boundary input: Notes@example.invalid'
        task = LegalAnalysisTask.objects.create(title='Synthetic task', input_text=original,
                                               created_by=self.actor)
        orchestrator = ComplianceOrchestrator(retriever=SimpleNamespace(
            retrieve_for_task=lambda task, actor=None: []))
        with patch.object(orchestrator.agent, 'analyze', wraps=orchestrator.agent.analyze) as analyze, \
                patch.object(orchestrator.agent, '_call_provider', return_value=None) as provider:
            result = orchestrator.run(task=task, actor=self.actor)
        context = analyze.call_args.kwargs['task']
        self.assertEqual(vars(context), {'id': task.id, 'title': task.title,
            'source_type': task.source_type, 'input_text': original})
        self.assertIn('Boundary input:', provider.call_args.args[0])
        self.assertNotIn('Notes@example.invalid', provider.call_args.args[0])
        self.assertNotIn('prompt', result['agent_run'].input_payload)
        task.refresh_from_db()
        self.assertEqual(task.status, 'completed')
        self.assertEqual(task.input_text, '')
        self.assertEqual(task.read_protected('input_text'), original)

    def test_protected_text_values_cross_storage_as_plain_json(self):
        from data_security.adapters.django.content import bind_content_protection, protect_text
        from data_security.adapters.persistence.fields import protect_stored_value

        bind_content_protection(self.components['protect_text'])
        self.addCleanup(bind_content_protection, None)
        value = protect_text('Boundary value: Notes@example.invalid')
        scalar = protect_stored_value(value)
        nested = protect_stored_value({'items': [value], 'count': 7})
        self.assertIs(type(scalar), str)
        self.assertEqual(nested, {'items': [scalar], 'count': 7})
        self.assertIs(type(nested['items'][0]), str)
        self.assertNotIn('Notes@example.invalid', json.dumps(nested))

    def test_equal_inputs_remain_distinct_and_admin_cannot_overwrite_sealed_fields(self):
        first = LegalAnalysisTask.objects.create(title='One', input_text='Same@example.invalid', created_by=self.actor)
        second = LegalAnalysisTask.objects.create(title='Two', input_text='Same@example.invalid', created_by=self.actor)
        self.assertNotEqual(first.security_envelopes, second.security_envelopes)
        first.status = 'completed'
        first.save()
        first.refresh_from_db()
        self.assertEqual(first.read_protected('input_text'), 'Same@example.invalid')
        request = RequestFactory().get('/admin/legal/legalanalysistask/')
        request.user = self.actor
        admin = LegalAnalysisTaskAdmin(LegalAnalysisTask, AdminSite())
        self.assertIn('input_text', admin.get_readonly_fields(request, first))
        self.assertNotIn('input_text', admin.search_fields)
        report = LegalReport.objects.create(title='Report', content='Same@example.invalid', generated_by=self.actor)
        self.assertIn('content', LegalReportAdmin(LegalReport, AdminSite()).get_readonly_fields(request, report))
        self.assertNotIn('content', LegalReportAdmin.search_fields)

    def test_role_owner_course_matrix_and_fk_write_scope(self):
        student = CTFUser.objects.create_user(username='legal-scope-student')
        other = CTFUser.objects.create_user(username='legal-scope-other')
        teacher = CTFUser.objects.create_user(username='legal-scope-teacher', role='teacher')
        course = LearningPath.objects.create(title='Legal scope', slug='legal-scope', difficulty='AP')
        denied = LearningPath.objects.create(title='Other scope', slug='legal-other-scope', difficulty='AP')
        tasks = {actor.pk: LegalAnalysisTask.objects.create(title='Synthetic task', input_text='Body@example.invalid', created_by=actor)
                 for actor in (student, other, teacher, self.actor)}
        for reviewer in (teacher, self.actor):
            CourseDataGrant.objects.create(actor=reviewer, student=student, course=course,
                granted_by=self.actor, expires_at=timezone.now() + timedelta(hours=1))
        view = LegalAnalysisTaskViewSet.as_view({'get': 'list'})
        for actor in (student, teacher, self.actor):
            for course_id in (None, course.pk, denied.pk):
                with self.subTest(role=actor.role, course=course_id):
                    expected = {tasks[actor.pk].pk}
                    if actor.role != 'student' and course_id == course.pk:
                        expected.add(tasks[student.pk].pk)
                    self.assertEqual(set(authorized_legal_objects(LegalAnalysisTask.objects.all(), actor,
                        course_id).values_list('pk', flat=True)), expected)
                    request = APIRequestFactory().get('/api/legal/analysis-tasks/',
                        {} if course_id is None else {'course': course_id})
                    force_authenticate(request, user=actor)
                    response = view(request)
                    if actor.role == 'student':
                        self.assertEqual(response.status_code, 403)
                    else:
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual({item['id'] for item in response.data['results']}, expected)
                        self.assertNotIn('Body@example.invalid', json.dumps(response.data))
        request = APIRequestFactory().post('/api/legal/evidence/', {
            'task': tasks[other.pk].pk, 'title': 'Attempt', 'evidence_type': 'manual', 'excerpt': 'Value'}, format='json')
        force_authenticate(request, user=teacher)
        response = LegalEvidenceViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 400)
        serializer = LegalEvidenceSerializer(data={'task': tasks[student.pk].pk,
            'title': 'No request', 'evidence_type': 'manual'})
        self.assertFalse(serializer.is_valid())

    def test_snapshot_subject_not_creator_controls_access(self):
        subject = CTFUser.objects.create_user(username='legal-fact-subject')
        task = LegalAnalysisTask.objects.create(title='Subject task', input_text='Subject@example.invalid', created_by=self.actor)
        LegalFactSnapshot.objects.create(source_kind='hybrid', scope={'subject_user_id': subject.pk},
            automated_facts={}, manual_notes='Subject@example.invalid', analysis_task=task,
            preview_hash='1' * 64, snapshot_hash='2' * 64, confirmed_by=self.actor)
        self.assertFalse(authorized_legal_objects(LegalAnalysisTask.objects.all(), self.actor).exists())
        self.assertTrue(authorized_legal_objects(LegalAnalysisTask.objects.all(), subject).exists())

    def test_plaintext_write_and_destructive_schema_rollback_are_refused(self):
        task = LegalAnalysisTask.objects.create(title='Synthetic', input_text='Protected@example.invalid', created_by=self.actor)
        with self.assertRaisesRegex(RuntimeError, 'FIELD_UPDATE'):
            LegalAnalysisTask.objects.filter(pk=task.pk).update(input_text='Raw@example.invalid')
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('UPDATE legal_legalanalysistask SET input_text=%s WHERE id=%s', ['Raw@example.invalid', task.pk])
        migration = import_module('legal.migrations.0003_field_envelopes')
        from django.apps import apps
        with self.assertRaisesRegex(RuntimeError, 'SEALED_FIELD_SCHEMA_ROLLBACK_REFUSED'):
            migration.refuse_sealed_rollback(apps, SimpleNamespace(connection=connection))

    def test_unbound_default_legacy_behavior_is_preserved(self):
        bind_field_storage(None)
        task = LegalAnalysisTask.objects.create(title='Legacy task', input_text='Legacy@example.invalid', created_by=self.actor)
        self.assertEqual(task.security_state, 'legacy-v0')
        self.assertEqual(task.read_protected('input_text'), 'Legacy@example.invalid')
        self.assertEqual(LegalAnalysisTaskSerializer(task).data['input_text'], 'Legacy@example.invalid')
