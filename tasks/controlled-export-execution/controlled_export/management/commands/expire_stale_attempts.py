from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from controlled_export.models import ExecutionAttempt, ExportExecution
from controlled_export.services import _outbox


class Command(BaseCommand):
    help = "Fence expired attempts without deleting their private candidate files."

    def handle(self, *args, **options):
        expired_ids = list(
            ExecutionAttempt.objects.filter(status="running", lease_expires_at__lte=timezone.now())
            .values_list("attempt_id", flat=True)
        )
        fenced = 0
        for attempt_id in expired_ids:
            with transaction.atomic():
                attempt = ExecutionAttempt.objects.select_for_update().select_related("execution").get(pk=attempt_id)
                execution = ExportExecution.objects.select_for_update().get(pk=attempt.execution_id)
                if attempt.status != "running" or attempt.lease_expires_at > timezone.now():
                    continue
                attempt.status = "stale"
                attempt.completed_at = timezone.now()
                attempt.error_code = "LEASE_EXPIRED"
                attempt.save(update_fields=["status", "completed_at", "error_code"])
                if execution.active_attempt_id == attempt.attempt_id and execution.state == "running":
                    execution.state = "failed"
                    execution.error_code = "LEASE_EXPIRED_RECONCILIATION_REQUIRED"
                    execution.completed_at = timezone.now()
                    execution.save(update_fields=["state", "error_code", "completed_at", "updated_at"])
                    _outbox(
                        "execution",
                        execution.execution_id,
                        "execution.failed",
                        {
                            "execution_id": str(execution.execution_id),
                            "attempt_id": str(attempt.attempt_id),
                            "error_code": execution.error_code,
                        },
                        execution.fencing_token,
                    )
                fenced += 1
        self.stdout.write(f"fenced_attempts={fenced}")
