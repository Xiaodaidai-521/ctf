from datetime import datetime, time, timedelta
from hashlib import sha256
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import LearningAuditJob, LearningEvent
from .services import ALGORITHM_VERSION, rebuild_user_analytics


# updated_at is renewed after each student. A live student transaction holds
# the job row lock, so this inactivity limit cannot steal work still writing.
JOB_STALE_AFTER = timedelta(minutes=5)


def get_period(days, reference_date=None):
    end_date = reference_date or timezone.localdate()
    start_date = end_date - timedelta(days=days - 1)
    zone = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_date, time.min), zone)
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), zone)
    return start, end


def get_idempotency_key(job_type, start, end, user_id=None):
    scope = user_id or 'all-students'
    value = f'{job_type}:{scope}:{start.isoformat()}:{end.isoformat()}:{ALGORITHM_VERSION}'
    return sha256(value.encode()).hexdigest()


def run_analytics_job(job_type='daily', days=30, reference_date=None, user_id=None):
    start, end = get_period(days, reference_date)
    key = get_idempotency_key(job_type, start, end, user_id)
    with transaction.atomic():
        job, created = LearningAuditJob.objects.select_for_update().get_or_create(
            idempotency_key=key,
            defaults={
                'job_id': uuid4().hex,
                'job_type': job_type,
                'target_user_id': user_id,
                'analysis_start_time': start,
                'analysis_end_time': end,
                'algorithm_version': ALGORITHM_VERSION,
            },
        )
        now = timezone.now()
        if not created and (job.status == 'completed' or (
                job.status == 'running' and job.updated_at > now - JOB_STALE_AFTER)):
            return job
        job.status = 'running'
        job.start_time = now
        job.end_time = None
        job.error_message = ''
        job.processed_user_count = 0
        job.processed_event_count = 0
        job.success_count = 0
        job.error_count = 0
        job.progress = 0
        job.attempt_count += 1
        job.save(update_fields=['status', 'start_time', 'end_time', 'error_message',
            'processed_user_count', 'processed_event_count', 'success_count',
            'error_count', 'progress', 'attempt_count', 'updated_at'])
        attempt = job.attempt_count

    users = get_user_model().objects.filter(role='student')
    if user_id:
        users = users.filter(id=user_id)
    users = list(users.order_by('id'))
    success_count = 0
    error_count = 0
    event_count = 0
    errors = []
    for index, user in enumerate(users, start=1):
        with transaction.atomic():
            job = LearningAuditJob.objects.select_for_update().get(pk=job.pk)
            if job.status != 'running' or job.attempt_count != attempt:
                return job  # A recovered attempt owns the snapshots and counters.
            try:
                # A failure rolls back this student's partial snapshot writes;
                # the outer transaction still records the failure/heartbeat.
                with transaction.atomic():
                    rebuild_user_analytics(user, start, end)
                    user_event_count = LearningEvent.objects.filter(
                        user=user, event_time__gte=start, event_time__lt=end).count()
                success_count += 1
                event_count += user_event_count
            except Exception as exc:
                error_count += 1
                errors.append(f'user={user.id}: {exc}')
            job.processed_user_count = index
            job.processed_event_count = event_count
            job.success_count = success_count
            job.error_count = error_count
            job.progress = round(index / max(len(users), 1) * 100, 2)
            job.save(update_fields=['processed_user_count', 'processed_event_count',
                'success_count', 'error_count', 'progress', 'updated_at'])
    with transaction.atomic():
        job = LearningAuditJob.objects.select_for_update().get(pk=job.pk)
        if job.status != 'running' or job.attempt_count != attempt:
            return job
        job.status = 'completed' if error_count == 0 else 'failed'
        job.end_time = timezone.now()
        job.error_message = '\n'.join(errors)[:4000]
        job.progress = 100
        job.save(update_fields=['status', 'end_time', 'error_message', 'progress', 'updated_at'])
        return job
