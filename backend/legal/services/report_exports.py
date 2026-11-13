"""Authorized report exports: redact in memory, persist AEAD bytes, recheck access on download."""
from datetime import timedelta
import hashlib
import os
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from audit.services import AuditLedgerService
from data_security.adapters.private_permissions import is_private_path
from data_security.runtime.crypto import get_cipher, restrict_path
from data_security.runtime.redaction import POLICY_VERSION, redact
from users.models import CTFUser
from users.permissions import authorized_users

from ..models import LegalAnalysisTask, LegalReport, LegalReportExport


MAX_EXPORT_BYTES = 8 * 1024 * 1024


class ExportUnavailable(APIException):
    status_code = 503
    default_detail = '导出文件暂时无法安全生成或读取，请稍后重试。'
    default_code = 'EXPORT_UNAVAILABLE'


def enabled():
    # Never route around the separate formal source/target/risk authorization chain.
    return bool(getattr(settings, 'DATA_PROTECTION_ENABLED', False)
                and not getattr(settings, 'DATA_SECURITY_FORMAL_MODE', False))


def is_exporter(actor):
    return bool(actor and actor.is_authenticated and actor.is_active
                and (actor.is_staff or actor.role == 'admin'))


def visible_reports(actor, course_id=None):
    """Use the same owner/course scope even if a caller has disabled field storage."""
    if not is_exporter(actor):
        return LegalReport.objects.none()
    # JSON scope IDs must use JSON-adapted values; a SQL integer subquery is not
    # comparable to a jsonb value on PostgreSQL.
    subjects = list(authorized_users(actor, course_id).values_list('pk', flat=True))
    tasks = LegalAnalysisTask.objects.filter(
        Q(fact_snapshots__scope__subject_user_id__in=subjects)
        | Q(fact_snapshots__isnull=True, created_by__in=subjects)).values('pk')
    return LegalReport.objects.filter(Q(task_id__in=tasks)
        | Q(task__isnull=True, generated_by__in=subjects))


def authorized_report(actor, report_id, course_id=None, *, lock=False):
    current = CTFUser.objects.filter(pk=getattr(actor, 'pk', None), is_active=True).first()
    if not is_exporter(current):
        raise PermissionDenied('当前账号无权导出报告。')
    queryset = visible_reports(current, course_id)
    if lock:
        queryset = queryset.select_for_update()
    report = queryset.filter(pk=report_id).first()
    if report is None:
        raise Http404
    return current, report


def artifact_path(record, *, create=False):
    root = Path(settings.DATA_PROTECTION_ROOT).absolute()
    for forbidden in (Path(settings.MEDIA_ROOT).resolve(), Path(settings.BASE_DIR).resolve().parent):
        if root.resolve().is_relative_to(forbidden):
            raise ValueError('EXPORT_ROOT_MUST_BE_PRIVATE')
    if create and not root.exists():
        root.mkdir(mode=0o700, parents=True)
        restrict_path(root, directory=True)
    if root.is_symlink() or not is_private_path(root, directory=True):
        raise ValueError('EXPORT_ROOT_PERMISSIONS')
    directory = root / 'report-exports'
    if create and not directory.exists():
        directory.mkdir(mode=0o700)
        restrict_path(directory, directory=True)
    if directory.is_symlink() or not is_private_path(directory, directory=True):
        raise ValueError('EXPORT_DIRECTORY_PERMISSIONS')
    path = directory / (str(record.pk) + '.bin')
    if path.is_symlink():
        raise ValueError('EXPORT_PATH_INVALID')
    return path


def context(record):
    return (f'legal-report-export/v1/{record.pk}/{record.report_id}/{record.requested_by_id}/'
            f'{record.course_id}/{record.policy_version}/{record.expires_at.isoformat()}/'
            f'{record.content_hash}/{record.byte_size}')


def read_artifact(record):
    if record.policy_version != POLICY_VERSION or not 0 < record.byte_size <= MAX_EXPORT_BYTES:
        raise ValueError('EXPORT_POLICY_INVALID')
    path = artifact_path(record)
    if not is_private_path(path) or path.stat().st_size > MAX_EXPORT_BYTES + 128:
        raise ValueError('EXPORT_FILE_INVALID')
    result = get_cipher().decrypt(path.read_bytes(), context(record))
    if len(result) != record.byte_size or hashlib.sha256(result).hexdigest() != record.content_hash:
        raise ValueError('EXPORT_CONTENT_INVALID')
    return result


def audit(record, actor, operation):
    AuditLedgerService.append_entry(event_category='report_export',
        object_type='legal.LegalReportExport', object_id=record.pk, actor=actor,
        payload={'operation': operation, 'export_id': str(record.pk), 'report_id': record.report_id,
                 'policy_version': record.policy_version, 'content_hash': record.content_hash,
                 'byte_size': record.byte_size})


def generate(actor, report_id, course_id=None):
    if not enabled():
        raise ExportUnavailable()
    path = None
    created = False
    try:
        with transaction.atomic():
            current, report = authorized_report(actor, report_id, course_id, lock=True)
            document = redact({'title': report.title, 'summary': report.summary,
                               'content': report.read_protected('content')})
            content = ('\n\n'.join(str(document[name]) for name in ('title', 'summary', 'content')) + '\n').encode('utf-8')
            if not 0 < len(content) <= MAX_EXPORT_BYTES:
                raise ValueError('EXPORT_TOO_LARGE')
            record = LegalReportExport(report=report, requested_by=current, course_id=course_id,
                policy_version=POLICY_VERSION, content_hash=hashlib.sha256(content).hexdigest(),
                byte_size=len(content), expires_at=timezone.now() + timedelta(hours=24))
            ciphertext = get_cipher().encrypt(content, context(record))
            path = artifact_path(record, create=True)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            created = True
            with os.fdopen(descriptor, 'wb') as stream:
                restrict_path(path)
                stream.write(ciphertext)
                stream.flush()
                os.fsync(stream.fileno())
            # Verify the actual saved bytes before publishing a successful record.
            read_artifact(record)
            authorized_report(actor, report.pk, course_id)
            record.save(force_insert=True)
            audit(record, current, 'generate')
            report.status = 'exported'
            report.save(update_fields=['status', 'updated_at'])
            return record
    except (PermissionDenied, Http404):
        if created:
            path.unlink(missing_ok=True)
        raise
    except Exception as error:
        if created:
            path.unlink(missing_ok=True)
        raise ExportUnavailable() from error


def download(actor, report_id, export_id):
    if not enabled():
        raise ExportUnavailable()
    try:
        export_id = UUID(str(export_id))
        report_id = int(report_id)
    except (TypeError, ValueError, AttributeError):
        raise Http404 from None
    with transaction.atomic():
        record = LegalReportExport.objects.select_for_update().filter(pk=export_id,
            report_id=report_id, requested_by_id=getattr(actor, 'pk', None),
            expires_at__gt=timezone.now()).first()
        if record is None:
            raise Http404
        current, _ = authorized_report(actor, report_id, record.course_id)
        try:
            content = read_artifact(record)
            # Access can expire or be revoked after generation; check on every delivery.
            authorized_report(actor, report_id, record.course_id)
            audit(record, current, 'download')
        except (PermissionDenied, Http404):
            raise
        except Exception as error:
            raise ExportUnavailable() from error
    response = HttpResponse(content, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="report-{report_id}.txt"'
    response['Cache-Control'] = 'no-store, private'
    response['X-Content-Type-Options'] = 'nosniff'
    response['X-Export-ID'] = str(record.pk)
    return response


def records(actor, offset=0):
    if not enabled() or not is_exporter(actor):
        return {'items': [], 'next_offset': None}
    rows = list(LegalReportExport.objects.filter(requested_by=actor,
        expires_at__gt=timezone.now()).select_related('report').order_by('-created_at', '-id')[offset:offset + 21])
    items = []
    for record in rows[:20]:
        try:
            _, report = authorized_report(actor, record.report_id, record.course_id)
        except (PermissionDenied, Http404):
            continue
        verified = False
        try:
            read_artifact(record)
            verified = True
        except (OSError, ValueError, RuntimeError, ImproperlyConfigured):
            pass
        items.append({'id': str(record.pk), 'kind': 'legal-report', 'report_id': record.report_id,
            'title': redact(report.title), 'state': 'generated' if verified else 'unknown',
            'can_execute': False, 'can_download': verified, 'expires_at': record.expires_at.isoformat(),
            'protection': {'redaction': 'completed' if verified else 'unknown',
                           'storage': 'encrypted' if verified else 'unknown'}})
    return {'items': items, 'next_offset': offset + 20 if len(rows) > 20 else None}
