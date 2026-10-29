from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from learning_map.models import CatalogVersion, TaskPackage
from users.models import CTFUser
from data_lab.catalog import CASES, TASK_A, TASK_B, digest
from data_lab.common import is_teacher
from data_lab.models import CasePackage


class Command(BaseCommand):
    help = 'Register candidate data-lab tasks in an existing draft catalog; never sign or publish.'

    def add_arguments(self, parser):
        parser.add_argument('--catalog', required=True)
        parser.add_argument('--owner', required=True, type=int)
        parser.add_argument('--capability', action='append', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        catalog = CatalogVersion.objects.filter(version=options['catalog'], status='draft').first()
        owner = CTFUser.objects.filter(pk=options['owner']).first()
        if catalog is None or owner is None or not is_teacher(owner):
            raise CommandError('需要既有草案目录与真实教师/管理员 owner。')
        capabilities = list(catalog.capabilities.filter(stable_id__in=options['capability']))
        if len(capabilities) != len(set(options['capability'])):
            raise CommandError('能力必须全部属于该目录；不创建替代能力。')
        for task_key, spec in CASES.items():
            task, created = TaskPackage.objects.select_for_update().get_or_create(task_key=task_key,
                version=spec['task_version'], defaults={
                    'catalog': catalog, 'title': spec['title'], 'track': 'data_security', 'status': 'draft',
                    'purpose': 'practice' if task_key == TASK_A else 'retest',
                    'execution_mode': 'readonly_decision', 'requires_milestone_i': False,
                    'materials': {'student_material_refs': [spec['fixture_id']]},
                    'validator': {'type': 'data_lab', 'version': spec['validator_version'], 'manual_required': True},
                    'hints': [{'level': i, 'source': 'card'} for i in range(1, 5)],
                    'acceptance': {'rules': ['server_saved_evidence'], 'execution': 'not_started', 'protection': 'not_assessed'},
                    'retest_task_keys': [TASK_B] if task_key == TASK_A else []})
            if task.catalog_id != catalog.pk:
                raise CommandError('该任务键/版本已属于其他目录，不迁移或复制。')
            if (task.status != 'draft' or task.execution_mode != 'readonly_decision'
                    or task.requires_milestone_i or task.validator.get('type') != 'data_lab'
                    or task.validator.get('version') != spec['validator_version']):
                raise CommandError('既有任务不是兼容的教学草案，不覆盖。')
            if created:
                task.capabilities.set(capabilities)
            elif set(task.capabilities.values_list('pk', flat=True)) != {c.pk for c in capabilities}:
                raise CommandError('既有任务能力绑定不同，不覆盖。')
            case, _ = CasePackage.objects.get_or_create(task=task, defaults={'owner': owner, 'material_digest': digest(spec)})
            if case.owner_id != owner.pk or case.material_digest != digest(spec):
                raise CommandError('既有案例owner或摘要不同，不覆盖。')
            if case.status != 'draft' or case.author_review or case.second_review:
                raise CommandError('既有案例已签收或不再是草案，不重新登记。')
            self.stdout.write(f'{task_key}: {case.status}; 未签收、未发布')
