"""One bounded batch for an external supervisor; deliberately no daemon/thread."""
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string

from mainline1.parsing import InputError
from mainline1.repository import DjangoRunRepository
from mainline1.worker import execute_one


class Command(BaseCommand):
    help = 'Recover expired leases and parse one queued task with a configured private asset owner.'

    def handle(self, **options):
        factory = getattr(settings, 'MAINLINE1_PRIVATE_SOURCE_FACTORY', None)
        if not factory:
            raise CommandError('PRIVATE_SOURCE_NOT_CONFIGURED')
        source = import_string(factory)()
        repository = DjangoRunRepository()
        recovered = repository.recover_expired(now=int(time.time()))
        for run_id in repository.pending():
            try:
                final = execute_one(repository, str(run_id), source)
            except InputError as exc:
                if exc.code in ('TASK_NOT_QUEUED', 'TASK_VERSION_CONFLICT', 'STALE_ATTEMPT'):
                    continue
                raise CommandError(exc.code) from None
            self.stdout.write(f'parsed_task={final.run_id} status={final.status} recovered={len(recovered)}')
            return
        self.stdout.write(f'queued=0 recovered={len(recovered)}')
