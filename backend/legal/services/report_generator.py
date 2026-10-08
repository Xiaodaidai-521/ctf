"""Compliance report generation service."""

import json
from typing import Iterable

from django.db import transaction

from ..models import LegalReport
from .ledger_service import LegalLedgerService


class ReportGenerator:
    """Generate legal reports from analysis tasks and findings."""

    @transaction.atomic
    def generate_analysis_report(self, *, task, findings: Iterable, evidence_items: Iterable, actor=None) -> LegalReport:
        """Create a draft analysis report and attach ledger evidence."""
        findings = list(findings)
        evidence_items = list(evidence_items)
        highest = findings[0].severity if findings else 'medium'
        summary = task.result_summary or f'合规分析完成，最高风险等级：{highest}。'
        content = self._render_markdown(task=task, findings=findings, evidence_items=evidence_items)
        report = LegalReport.objects.create(
            task=task,
            report_type='analysis',
            title=f'{task.title} - 合规分析报告',
            summary=summary,
            content=content,
            status='draft',
            generated_by=actor,
            metadata={
                'finding_count': len(findings),
                'evidence_count': len(evidence_items),
                'highest_severity': highest,
            },
        )
        LegalLedgerService.attach_report_ledger(report, actor=actor, action='generate')
        return report

    def _render_markdown(self, *, task, findings, evidence_items) -> str:
        finding_payload = [
            {
                'title': item.title,
                'severity': item.severity,
                'score': item.score,
                'recommendation': item.recommendation,
            }
            for item in findings
        ]
        evidence_payload = [
            {
                'title': item.title,
                'object_type': item.object_type,
                'object_id': item.object_id,
                'relevance_score': item.relevance_score,
            }
            for item in evidence_items
        ]
        return '\n'.join([
            f'# {task.title} 合规分析报告',
            '',
            '## 分析对象',
            task.input_text or '(未提供正文)',
            '',
            '## 风险发现',
            json.dumps(finding_payload, ensure_ascii=False, indent=2),
            '',
            '## 证据引用',
            json.dumps(evidence_payload, ensure_ascii=False, indent=2),
        ])
