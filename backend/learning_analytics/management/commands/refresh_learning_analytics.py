from datetime import date

from django.core.management.base import BaseCommand, CommandError

from learning_analytics.scheduler import run_analytics_job


class Command(BaseCommand):
    help = 'Rebuild learning analytics snapshots from recorded learning events.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, choices=[7, 30, 90], default=30)
        parser.add_argument('--date', type=str)
        parser.add_argument('--user-id', type=int)
        parser.add_argument('--job-type', choices=['daily', 'weekly', 'monthly', 'manual'], default='manual')

    def handle(self, *args, **options):
        reference_date = None
        if options['date']:
            try:
                reference_date = date.fromisoformat(options['date'])
            except ValueError as exc:
                raise CommandError('--date must use YYYY-MM-DD.') from exc
        job = run_analytics_job(job_type=options['job_type'], days=options['days'], reference_date=reference_date, user_id=options['user_id'])
        self.stdout.write(self.style.SUCCESS(f'job={job.job_id} status={job.status} users={job.success_count} errors={job.error_count}'))
