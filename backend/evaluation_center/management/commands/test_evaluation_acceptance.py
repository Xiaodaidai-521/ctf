from django.core.management import call_command
from django.core.management.base import BaseCommand

from evaluation_center.acceptance import SCENARIOS, VERSION, test_labels


class Command(BaseCommand):
    help = 'Run the fixed M8 phase-one regression selectors in a Django test database.'

    def handle(self, *args, **options):
        self.stdout.write(VERSION + ' — developer regression, not independent final acceptance')
        for row in SCENARIOS:
            if row['dependencies']:
                self.stdout.write(f"Scenario {row['id']} remaining: {'; '.join(row['dependencies'])}")
        call_command('test', *test_labels(), interactive=False, verbosity=options['verbosity'])
