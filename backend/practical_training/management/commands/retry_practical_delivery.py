from django.core.management.base import BaseCommand

from practical_training.delivery import retry_notice
from skill_review.models import DownstreamNotice


class Command(BaseCommand):
    help = '重试模块五证据的模块一事实交接，不重执行靶场或修复验证'

    def handle(self, *args, **options):
        sent = failed = 0
        for notice in DownstreamNotice.objects.filter(notice_key__startswith='m5:', status='failed', target='module1'):
            result = retry_notice(notice)
            if result.status == 'sent':
                sent += 1
            else:
                failed += 1
        self.stdout.write(f'sent={sent} failed={failed}')
