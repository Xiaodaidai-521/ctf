"""Minimal in-memory DB reproduction while PostgreSQL checkpoint I/O is busy."""
from datetime import timedelta
from io import StringIO
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
from tools.full_audit.run import clean_env
isolated = clean_env()
os.environ.clear()
os.environ.update(isolated)
from django.conf import settings
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
import django
django.setup()
from ctf_backend.security_bootstrap import bind_legacy_for_tests
from data_security.contracts import Environment
bind_legacy_for_tests(environment=Environment.TEST)
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone
from users.models import CTFUser
from learning_analytics.models import LearningAuditJob
from learning_analytics.scheduler import get_period, get_idempotency_key, run_analytics_job

with connection.schema_editor() as editor:
    editor.create_model(CTFUser)
    editor.create_model(LearningAuditJob)
student = CTFUser.objects.create_user(username='scratch-runtime-audit', role='student')
start, end = get_period(30)
old = LearningAuditJob.objects.create(job_id='stale-scratch', job_type='manual',
    idempotency_key=get_idempotency_key('manual', start, end, student.pk), target_user=student,
    status='running', attempt_count=1, analysis_start_time=start, analysis_end_time=end)
LearningAuditJob.objects.filter(pk=old.pk).update(updated_at=timezone.now() - timedelta(hours=1))
with patch('learning_analytics.scheduler.rebuild_user_analytics', side_effect=RuntimeError('scratch failure')) as rebuild:
    result = run_analytics_job(job_type='manual', user_id=student.pk)
    stale = {'same_job': result.pk == old.pk, 'status': result.status,
             'attempt_count': result.attempt_count, 'rebuild_called': rebuild.called}

output = StringIO()
raised = False
with patch('learning_analytics.scheduler.rebuild_user_analytics', side_effect=RuntimeError('scratch failure')):
    try:
        call_command('refresh_learning_analytics', days=7, user_id=student.pk, stdout=output)
    except CommandError:
        raised = True
failed = LearningAuditJob.objects.exclude(pk=old.pk).get()
data = {'scope': 'isolated SQLite in memory; actual User/Job models; failing rebuild substitute, no snapshots or external calls',
        'stale_job': stale, 'failed_command': {'status': failed.status,
            'command_error_raised': raised, 'stdout': output.getvalue()},
        'production_database_accessed': False}
label = sys.argv[1] if len(sys.argv) > 1 else 'before-confirmed'
(Path(__file__).resolve().parent / ('sqlite-' + label + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(data, ensure_ascii=False, indent=2))
