from django.core.management.base import BaseCommand
from django.utils import timezone

from practical_training.lifecycle import TERMINAL_STATES, expire_due, reconcile_cleanup
from practical_training.models import LabAssignment


class Command(BaseCommand):
    help = '回收到期的平台授权；外部容器和网络仍待运维回收，不宣称已物理销毁'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if options['dry_run']:
            count = LabAssignment.objects.filter(expires_at__lte=timezone.now()).exclude(state__in=TERMINAL_STATES).count()
            self.stdout.write(f'Would expire {count} platform assignments.')
        else:
            self.stdout.write(f'Expired {expire_due()} platform assignments; '
                              f'{reconcile_cleanup()} runtime cleanup receipts; others require operator.')
