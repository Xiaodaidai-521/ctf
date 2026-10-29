from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from challenges.models import Challenge
from learning_map.models import Capability, CatalogVersion, TaskPackage
from practical_training.curriculum import HINTS, MATERIAL, REPAIR_MATERIAL
from practical_training.models import ChallengeMapping
from practical_training.services import CHALLENGE_VERIFIER, REPAIR_VERIFIER


class Command(BaseCommand):
    help = '为现有目录与能力创建模块五候选任务，不冻结、不伪造课程/环境验收'

    def add_arguments(self, parser):
        parser.add_argument('--catalog', required=True)
        parser.add_argument('--capability', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        catalog = CatalogVersion.objects.filter(version=options['catalog']).first()
        capability = Capability.objects.filter(catalog=catalog, stable_id=options['capability'], track='network').first()
        challenge = Challenge.objects.filter(docker_image=settings.JUICE_SHOP_IMAGE).first()
        if not catalog or not capability or not challenge:
            raise CommandError('需要现有网络安全目录能力及 import_juice_shop 导入的挑战。')
        tasks = []
        for key, title, purpose, material, version in (
            ('M5-JUICE-DOCUMENT', '机密文档暴露核验', 'verification', MATERIAL, CHALLENGE_VERIFIER),
            ('M5-DOCUMENT-REPAIR', '新场景：资料库访问控制修复方案', 'retest', REPAIR_MATERIAL, REPAIR_VERIFIER),
        ):
            task, created = TaskPackage.objects.get_or_create(task_key=key, version='1.0.0', defaults={
                'catalog': catalog, 'title': title, 'track': 'network', 'purpose': purpose,
                'execution_mode': 'isolated_challenge', 'status': 'draft',
                'environment_available': False, 'challenge': challenge, 'materials': material,
                'hints': HINTS, 'validator': {'type': 'server_verifier', 'version': version},
                'acceptance': {'evidence': '服务端绑定证据', 'manual_required': False,
                               'scope': material['scope'], 'environment_isolation_verified': False},
                'retest_task_keys': ['M5-DOCUMENT-REPAIR'] if purpose == 'verification' else [],
            })
            if task.catalog_id != catalog.pk:
                raise CommandError('任务键已在另一目录中使用，请创建新任务版本，不覆盖历史。')
            if created:
                task.capabilities.set([capability])
            tasks.append(task)
        mapping, _ = ChallengeMapping.objects.get_or_create(task=tasks[0], defaults={'repair_task': tasks[1]})
        self.stdout.write(f'Candidate mapping {mapping.pk}; course review and environment release required.')
