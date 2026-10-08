"""Tests for legal compliance business APIs and services."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent, AuditLedgerEntry
from audit.services import AuditLedgerService
from challenges.container_audit import record_container_audit
from legal_kb.models import LegalDocument
from legal_kb.services.hashing import sha256_text
from legal_kb.services.ingestion_service import LegalKbIngestionService

from .models import (
    ComplianceAgentRun,
    DataProcessingActivity,
    LegalAnalysisTask,
    LegalEvidence,
    LegalProtocol,
    LegalProtocolVersion,
    LegalReport,
    LegalRiskFinding,
    UserConsentRecord,
)
from .services.compliance_orchestrator import ComplianceOrchestrator
from .services.consent_service import ConsentService, compute_content_hash
from .services.risk_evaluator import RiskEvaluator


User = get_user_model()


class FailingRetriever:
    """Test retriever that simulates an infrastructure failure."""

    def retrieve_for_task(self, task, actor=None):
        raise RuntimeError('retrieval backend unavailable')


class FixedRetriever:
    """Test retriever that returns deterministic legal references."""

    def __init__(self, evidence):
        self.evidence = evidence

    def retrieve_for_task(self, task, actor=None):
        return self.evidence


class RiskEvaluatorTests(TestCase):
    """Risk scoring should be driven by the reviewed scenario, not legal references alone."""

    def test_legal_reference_keywords_do_not_force_critical_risk(self):
        evidence = [{
            'title': '个人信息保护法参考条款',
            'text': '敏感个人信息、未成年人、跨境提供个人信息应当遵守更严格规则。',
            'score': 0.9,
        }]

        assessment = RiskEvaluator().evaluate(
            text='靶场日志留存用于安全审计，需确认保存周期和访问范围。',
            evidence=evidence,
        )

        self.assertEqual(assessment.severity, 'low')
        self.assertNotIn('敏感个人信息', assessment.matched_keywords)

    def test_control_evidence_terms_do_not_create_medium_risk(self):
        assessment = RiskEvaluator().evaluate(
            text='用户协议条款已告知处理目的，已有同意记录、日志保存周期和审计哈希链。',
            evidence=[],
        )

        self.assertEqual(assessment.severity, 'low')
        self.assertNotIn('同意', assessment.matched_keywords)
        self.assertNotIn('日志', assessment.matched_keywords)

    def test_missing_consent_or_retention_stays_medium_risk(self):
        assessment = RiskEvaluator().evaluate(
            text='平台处理个人信息但未取得同意，且无保存周期说明。',
            evidence=[],
        )

        self.assertEqual(assessment.severity, 'medium')
        self.assertIn('未取得同意', assessment.matched_keywords)

    def test_actual_illegal_data_disclosure_stays_critical(self):
        assessment = RiskEvaluator().evaluate(
            text='发现用户个人信息泄露并被非法提供给第三方。',
            evidence=[],
        )

        self.assertEqual(assessment.severity, 'critical')
        self.assertIn('泄露', assessment.matched_keywords)


class ConsentServiceTests(TestCase):
    """Protocol publishing and consent should produce evidence."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin',
            password='pass12345',
            role='admin',
            is_staff=True,
        )
        self.student = User.objects.create_user(
            username='student',
            password='pass12345',
            role='student',
        )
        self.protocol = LegalProtocol.objects.create(
            key='privacy',
            name='Privacy Policy',
            protocol_type='privacy_policy',
        )

    def test_publish_protocol_version_sets_hash(self):
        version = ConsentService.publish_protocol_version(
            protocol=self.protocol,
            version='1.0',
            title='Privacy Policy v1',
            content='privacy content',
            actor=self.admin,
        )

        self.assertTrue(version.is_published)
        self.assertEqual(version.content_hash, compute_content_hash('privacy content'))
        self.assertEqual(AuditLedgerEntry.objects.count(), 1)

    def test_sign_protocol_creates_consent_and_ledger(self):
        version = LegalProtocolVersion.objects.create(
            protocol=self.protocol,
            version='1.0',
            title='Privacy Policy v1',
            content='privacy content',
            content_hash=compute_content_hash('privacy content'),
            is_published=True,
        )
        consent = ConsentService.sign_protocol(
            user=self.student,
            protocol_version=version,
            evidence={'checkbox': True},
        )

        self.assertEqual(consent.user, self.student)
        self.assertIsNotNone(consent.ledger_entry)
        self.assertTrue(AuditLedgerService.verify_chain().is_valid)


class LegalApiTests(TestCase):
    """Legal APIs should enforce roles and write ledger evidence."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin',
            password='pass12345',
            role='admin',
            is_staff=True,
        )
        self.teacher = User.objects.create_user(
            username='teacher',
            password='pass12345',
            role='teacher',
        )
        self.student = User.objects.create_user(
            username='student',
            password='pass12345',
            role='student',
        )
        self.protocol = LegalProtocol.objects.create(
            key='privacy',
            name='Privacy Policy',
            protocol_type='privacy_policy',
        )
        self.version = LegalProtocolVersion.objects.create(
            protocol=self.protocol,
            version='1.0',
            title='Privacy Policy v1',
            content='privacy content',
            content_hash=compute_content_hash('privacy content'),
            is_published=True,
        )

    def test_student_can_sign_protocol(self):
        self.client.force_authenticate(self.student)
        response = self.client.post('/api/legal/consents/sign/', {
            'protocol_version_id': self.version.id,
            'consent_method': 'checkbox',
            'evidence': {'checkbox': True},
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(UserConsentRecord.objects.count(), 1)
        self.assertEqual(AuditLedgerEntry.objects.filter(event_category='consent_sign').count(), 1)

    def test_student_cannot_create_data_processing_activity(self):
        self.client.force_authenticate(self.student)
        response = self.client.post('/api/legal/data-processing/', {
            'name': 'Login analytics',
            'processing_type': 'collect',
            'purpose': 'Security analytics',
        }, format='json')

        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_data_processing_activity_with_ledger(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/legal/data-processing/', {
            'name': 'Login analytics',
            'processing_type': 'collect',
            'data_categories': ['login_ip', 'user_agent'],
            'purpose': 'Security analytics',
            'legal_basis': 'platform security',
            'risk_level': 'medium',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        activity = DataProcessingActivity.objects.get()
        self.assertIsNotNone(activity.ledger_entry)
        self.assertEqual(activity.created_by, self.admin)

    def test_teacher_can_create_analysis_task(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post('/api/legal/analysis-tasks/', {
            'title': 'Review resource upload flow',
            'source_type': 'manual',
            'input_text': 'Check whether user consent is recorded.',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(AuditLedgerEntry.objects.filter(event_category='legal_analysis').count(), 1)

    def test_teacher_can_run_compliance_analysis(self):
        full_text = '第一条 为了保护个人信息权益。第二条 处理个人信息应当合法、正当、必要，并取得同意。'
        document = LegalDocument.objects.create(
            title='Personal Information Protection Law',
            document_type='law',
            source_hash=sha256_text(full_text),
            full_text=full_text,
            created_by=self.admin,
        )
        LegalKbIngestionService().ingest_document(document, actor=self.admin)
        task = LegalAnalysisTask.objects.create(
            title='Review personal information processing',
            source_type='manual',
            input_text='The platform collects personal information and needs user consent evidence.',
            created_by=self.teacher,
        )

        self.client.force_authenticate(self.teacher)
        response = self.client.post(f'/api/legal/analysis-tasks/{task.id}/run_analysis/')

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'completed')
        self.assertEqual(LegalRiskFinding.objects.filter(task=task).count(), 1)
        self.assertGreaterEqual(LegalEvidence.objects.filter(task=task).count(), 1)
        self.assertEqual(ComplianceAgentRun.objects.filter(task=task).count(), 1)
        self.assertEqual(LegalReport.objects.filter(task=task).count(), 1)
        self.assertGreaterEqual(
            AuditLedgerEntry.objects.filter(event_category='legal_analysis').count(),
            2,
        )

        runs_response = self.client.get('/api/legal/agent-runs/', {'task': task.id})
        self.assertEqual(runs_response.status_code, 200)
        self.assertEqual(len(runs_response.data['results']), 1)

    def test_failed_analysis_persists_failed_status_and_audit_event(self):
        task = LegalAnalysisTask.objects.create(
            title='Failing compliance task',
            source_type='manual',
            input_text='Trigger a retriever failure.',
            created_by=self.teacher,
        )

        with self.assertRaises(RuntimeError):
            ComplianceOrchestrator(retriever=FailingRetriever()).run(task=task, actor=self.teacher)

        task.refresh_from_db()
        self.assertEqual(task.status, 'failed')
        self.assertIn('retrieval backend unavailable', task.error_message)
        self.assertTrue(
            AuditEvent.objects.filter(
                category='legal_analysis',
                summary__contains='failed',
                detail__task_id=task.id,
            ).exists()
        )

    def test_rerun_replaces_previous_findings_for_same_task(self):
        task = LegalAnalysisTask.objects.create(
            title='Rerun compliance task',
            source_type='manual',
            input_text='靶场日志留存用于安全审计，需确认保存周期。',
            created_by=self.teacher,
        )
        retriever = FixedRetriever([{
            'title': '个人信息保护法参考条款',
            'text': '敏感个人信息、未成年人、跨境提供个人信息应当遵守更严格规则。',
            'score': 0.9,
            'source_type': 'legal_clause',
        }])
        orchestrator = ComplianceOrchestrator(retriever=retriever)

        orchestrator.run(task=task, actor=self.teacher)
        orchestrator.run(task=task, actor=self.teacher)

        self.assertEqual(LegalRiskFinding.objects.filter(task=task).count(), 1)
        finding = LegalRiskFinding.objects.get(task=task)
        self.assertEqual(finding.severity, 'low')

    def test_student_cannot_run_compliance_analysis(self):
        task = LegalAnalysisTask.objects.create(
            title='Student forbidden task',
            source_type='manual',
            input_text='Check consent.',
            created_by=self.teacher,
        )

        self.client.force_authenticate(self.student)
        response = self.client.post(f'/api/legal/analysis-tasks/{task.id}/run_analysis/')

        self.assertEqual(response.status_code, 403)

    def test_student_cannot_read_agent_runs(self):
        task = LegalAnalysisTask.objects.create(
            title='Agent run visibility',
            source_type='manual',
            input_text='Check consent.',
            created_by=self.teacher,
        )
        ComplianceAgentRun.objects.create(
            task=task,
            provider='fallback',
            model='rules-v1',
            input_payload={'task_id': task.id},
            output_payload={'content': 'ok'},
        )

        self.client.force_authenticate(self.student)
        response = self.client.get('/api/legal/agent-runs/')

        self.assertEqual(response.status_code, 403)

    def test_teacher_can_read_container_audits(self):
        event, ledger = record_container_audit(
            action='start_succeeded',
            result='success',
            user=self.student,
            challenge=None,
            image='ctf/example:latest',
            port=18080,
            network='ctf-network',
        )

        self.client.force_authenticate(self.teacher)
        response = self.client.get('/api/legal/container-audits/')

        self.assertEqual(response.status_code, 200)
        payload = response.data['results'][0]
        self.assertEqual(payload['id'], event.id)
        self.assertEqual(payload['action'], 'start_succeeded')
        self.assertEqual(payload['image'], 'ctf/example:latest')
        self.assertEqual(payload['port'], 18080)
        self.assertEqual(payload['ledger_hash'], ledger.current_hash)

    def test_student_cannot_read_container_audits(self):
        record_container_audit(action='start_requested', result='requested')

        self.client.force_authenticate(self.student)
        response = self.client.get('/api/legal/container-audits/')

        self.assertEqual(response.status_code, 403)

    def test_admin_can_export_report(self):
        report = LegalReport.objects.create(
            title='Monthly compliance report',
            report_type='periodic',
            summary='Summary',
            content='Content',
            generated_by=self.admin,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/legal/reports/{report.id}/export/')

        self.assertEqual(response.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, 'exported')
        self.assertEqual(AuditLedgerEntry.objects.filter(event_category='report_export').count(), 1)
