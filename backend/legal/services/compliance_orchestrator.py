"""Compliance analysis orchestration service."""

from typing import Dict, List

from django.db import transaction
from django.utils import timezone

from audit.models import AuditEvent
from audit.services import AuditLedgerService

from ..models import ComplianceAgentRun, LegalEvidence, LegalRiskFinding
from .compliance_agent import ComplianceAgent
from .legal_retriever import LegalRetriever
from .report_generator import ReportGenerator
from .risk_evaluator import RiskEvaluator


class ComplianceOrchestrator:
    """Coordinate retrieval, risk evaluation, agent output, evidence, and reports."""

    def __init__(
        self,
        *,
        retriever: LegalRetriever = None,
        evaluator: RiskEvaluator = None,
        agent: ComplianceAgent = None,
        report_generator: ReportGenerator = None,
    ):
        self.retriever = retriever or LegalRetriever()
        self.evaluator = evaluator or RiskEvaluator()
        self.agent = agent or ComplianceAgent()
        self.report_generator = report_generator or ReportGenerator()

    def run(self, *, task, actor=None) -> Dict:
        """Run a compliance analysis task end to end."""
        self._mark_running(task)

        try:
            retrieved = self.retriever.retrieve_for_task(task, actor=actor)
            assessment = self.evaluator.evaluate(text=task.input_text or task.title, evidence=retrieved)
            agent_output = self.agent.analyze(task=task, evidence=retrieved, assessment=assessment)
            return self._persist_success(
                task=task,
                actor=actor,
                retrieved=retrieved,
                assessment=assessment,
                agent_output=agent_output,
            )
        except Exception as exc:
            self._mark_failed(task=task, actor=actor, error=exc)
            raise

    def _mark_running(self, task) -> None:
        task.status = 'running'
        task.started_at = timezone.now()
        task.completed_at = None
        task.error_message = ''
        task.save(update_fields=['status', 'started_at', 'completed_at', 'error_message', 'updated_at'])

    @transaction.atomic
    def _persist_success(self, *, task, actor, retrieved, assessment, agent_output) -> Dict:
        self._clear_previous_analysis(task)
        finding = self._create_finding(task=task, assessment=assessment)
        evidence_items = self._create_evidence_items(
            task=task,
            finding=finding,
            retrieved=retrieved,
        )
        run = ComplianceAgentRun.objects.create(
            task=task,
            agent_id=agent_output['agent_id'],
            provider=agent_output['provider'],
            model=agent_output['model'],
            input_payload=agent_output['input_payload'],
            output_payload=agent_output['output_payload'],
            success=agent_output['success'],
            error_message=agent_output['error_message'],
            duration_ms=agent_output['duration_ms'],
        )
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.result_summary = agent_output['output_payload']['content'][:1000]
        task.metadata = {
            **(task.metadata or {}),
            'last_run_id': run.id,
            'risk_score': assessment.score,
            'risk_severity': assessment.severity,
            'evidence_count': len(evidence_items),
        }
        task.save(update_fields=['status', 'completed_at', 'result_summary', 'metadata', 'updated_at'])
        report = self.report_generator.generate_analysis_report(
            task=task,
            findings=[finding],
            evidence_items=evidence_items,
            actor=actor,
        )
        self._write_audit(task=task, actor=actor, finding=finding, report=report)
        return {
            'task': task,
            'finding': finding,
            'evidence': evidence_items,
            'agent_run': run,
            'report': report,
        }

    def _clear_previous_analysis(self, task) -> None:
        LegalEvidence.objects.filter(task=task).delete()
        LegalRiskFinding.objects.filter(task=task).delete()

    @transaction.atomic
    def _mark_failed(self, *, task, actor, error: Exception) -> None:
        now = timezone.now()
        task.__class__.objects.filter(pk=task.pk).update(
            status='failed',
            error_message=str(error),
            completed_at=now,
            updated_at=now,
        )
        AuditEvent.log(
            category='legal_analysis',
            summary=f'Legal analysis failed: {task.title}',
            user=actor,
            detail={'task_id': task.id, 'error': str(error)},
        )
        task.refresh_from_db(fields=['status', 'error_message', 'completed_at', 'updated_at'])

    def _create_finding(self, *, task, assessment) -> LegalRiskFinding:
        return LegalRiskFinding.objects.create(
            task=task,
            title=assessment.title,
            description=assessment.description,
            severity=assessment.severity,
            likelihood=assessment.likelihood,
            impact=assessment.impact,
            score=assessment.score,
            recommendation=assessment.recommendation,
        )

    def _create_evidence_items(self, *, task, finding, retrieved: List[Dict]) -> List[LegalEvidence]:
        items = []
        for item in retrieved:
            evidence_type = 'legal_clause' if item.get('source_type') == 'legal_clause' else 'manual'
            evidence = LegalEvidence.objects.create(
                task=task,
                risk_finding=finding,
                evidence_type=evidence_type,
                object_type=item.get('source_type', ''),
                object_id=str(item.get('object_id') or item.get('id') or ''),
                title=item.get('title') or 'Legal evidence',
                excerpt=item.get('text', '')[:2000],
                relevance_score=item.get('score') or 0,
                metadata=item.get('metadata') or {},
            )
            items.append(evidence)
        if not items:
            items.append(LegalEvidence.objects.create(
                task=task,
                risk_finding=finding,
                evidence_type='manual',
                title='Evidence gap',
                excerpt='未检索到可引用的知识库证据，需要补充法规、案例或平台审计材料。',
                relevance_score=0,
                metadata={'gap': True},
            ))
        return items

    def _write_audit(self, *, task, actor, finding, report) -> None:
        AuditEvent.log(
            category='legal_analysis',
            summary=f'Legal analysis completed: {task.title}',
            user=actor,
            detail={
                'task_id': task.id,
                'finding_id': finding.id,
                'report_id': report.id,
                'severity': finding.severity,
                'score': finding.score,
            },
        )
        AuditLedgerService.append_entry(
            event_category='legal_analysis',
            object_type='legal.LegalAnalysisTask',
            object_id=task.id,
            actor=actor,
            payload={
                'action': 'run_compliance_analysis',
                'task_id': task.id,
                'finding_id': finding.id,
                'report_id': report.id,
                'severity': finding.severity,
                'score': finding.score,
            },
        )
