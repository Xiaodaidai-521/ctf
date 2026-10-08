"""Services that create compliance records with audit evidence."""

from typing import Any, Dict

from django.db import transaction

from audit.models import AuditEvent
from audit.services import AuditLedgerService

from ..models import DataProcessingActivity, LegalReport, ViolationRecord


class LegalLedgerService:
    """Create legal business records and write audit ledger entries."""

    @staticmethod
    @transaction.atomic
    def attach_data_processing_ledger(activity: DataProcessingActivity, actor=None) -> DataProcessingActivity:
        """Attach a hash-chain entry to a data processing activity."""
        if activity.ledger_entry_id:
            return activity
        ledger_entry = AuditLedgerService.append_entry(
            event_category='data_processing',
            object_type='legal.DataProcessingActivity',
            object_id=activity.id,
            actor=actor or activity.created_by,
            payload={
                'activity_id': activity.id,
                'name': activity.name,
                'processing_type': activity.processing_type,
                'data_categories': activity.data_categories,
                'purpose': activity.purpose,
                'legal_basis': activity.legal_basis,
                'risk_level': activity.risk_level,
            },
        )
        activity.ledger_entry = ledger_entry
        activity.save(update_fields=['ledger_entry'])
        AuditEvent.log(
            category='data_processing',
            summary=f'Data processing activity recorded: {activity.name}',
            user=actor or activity.created_by,
            detail={'activity_id': activity.id},
        )
        return activity

    @staticmethod
    @transaction.atomic
    def attach_violation_ledger(record: ViolationRecord, actor=None) -> ViolationRecord:
        """Attach a hash-chain entry to a violation record."""
        if record.ledger_entry_id:
            return record
        ledger_entry = AuditLedgerService.append_entry(
            event_category='violation_record',
            object_type='legal.ViolationRecord',
            object_id=record.id,
            actor=actor or record.created_by,
            payload={
                'violation_id': record.id,
                'title': record.title,
                'severity': record.severity,
                'status': record.status,
                'related_task_id': record.related_task_id,
            },
        )
        record.ledger_entry = ledger_entry
        record.save(update_fields=['ledger_entry'])
        AuditEvent.log(
            category='violation_record',
            summary=f'Violation record created: {record.title}',
            user=actor or record.created_by,
            detail={'violation_id': record.id},
        )
        return record

    @staticmethod
    @transaction.atomic
    def attach_report_ledger(report: LegalReport, actor=None, action: str = 'generate') -> LegalReport:
        """Attach a hash-chain entry to a legal report."""
        if report.ledger_entry_id:
            return report
        ledger_entry = AuditLedgerService.append_entry(
            event_category='report_export' if action == 'export' else 'legal_analysis',
            object_type='legal.LegalReport',
            object_id=report.id,
            actor=actor or report.generated_by,
            payload={
                'report_id': report.id,
                'task_id': report.task_id,
                'title': report.title,
                'report_type': report.report_type,
                'status': report.status,
                'action': action,
            },
        )
        report.ledger_entry = ledger_entry
        report.save(update_fields=['ledger_entry'])
        AuditEvent.log(
            category='report_export' if action == 'export' else 'legal_analysis',
            summary=f'Legal report {action}: {report.title}',
            user=actor or report.generated_by,
            detail={'report_id': report.id, 'task_id': report.task_id},
        )
        return report

    @staticmethod
    def build_report_content(*, title: str, summary: str, findings: Any = None) -> Dict[str, Any]:
        """Build a simple structured report payload for early implementation."""
        return {
            'title': title,
            'summary': summary,
            'findings': findings or [],
        }
