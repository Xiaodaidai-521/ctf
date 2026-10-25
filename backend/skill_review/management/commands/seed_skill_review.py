"""Attach runnable verification checks to the candidate task packages.

Module 1 defines the task contract; module 6 owns the concrete verifier used
for first-phase exercises.  This command is idempotent and only updates the
``validator`` field of the candidate tasks — it never changes task status,
materials or review state.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from learning_map.models import CatalogVersion, TaskPackage


DATA_CHECKS = [
    {
        'id': 'basis',
        'label': '引用适用依据条款',
        'field': 'basis_clause',
        'required': True,
        'cause': 'concept_unclear',
    },
    {
        'id': 'personal_fields',
        'label': '标出个人信息字段',
        'field': 'personal_info_fields',
        'contains_all': ['phone', 'id_card'],
        'cause': 'scope_error',
    },
    {
        'id': 'sensitive_fields',
        'label': '标出敏感个人信息字段',
        'field': 'sensitive_fields',
        'contains_all': ['id_card'],
        'cause': 'scope_error',
    },
    {
        'id': 'export_decision',
        'label': '模拟导出决策为拒绝',
        'field': 'export_decision',
        'equals': 'reject',
        'cause': 'concept_unclear',
    },
    {
        'id': 'export_reason',
        'label': '记录决策理由',
        'field': 'export_reason',
        'required': True,
        'cause': 'evidence_insufficient',
    },
    {
        'id': 'audit_note',
        'label': '记录审计要点',
        'field': 'audit_note',
        'required': True,
        'cause': 'evidence_insufficient',
    },
]

RETEST_CHECKS = [
    {
        'id': 'basis',
        'label': '引用适用依据条款',
        'field': 'basis_clause',
        'required': True,
        'cause': 'concept_unclear',
    },
    {
        'id': 'sensitive_fields',
        'label': '标出新场景中的敏感字段',
        'field': 'sensitive_fields',
        'contains_all': ['phone', 'ip_address'],
        'cause': 'scope_error',
    },
    {
        'id': 'export_decision',
        'label': '模拟导出决策为拒绝',
        'field': 'export_decision',
        'equals': 'reject',
        'cause': 'concept_unclear',
    },
    {
        'id': 'export_reason',
        'label': '记录决策理由',
        'field': 'export_reason',
        'required': True,
        'cause': 'evidence_insufficient',
    },
]

VALIDATORS = {
    'TASK-DS-CUSTOMER-TABLE-001': {
        'version': 'm6-rules-v1-candidate',
        'type': 'rules+teacher_rubric',
        'manual_required': True,
        'checks': DATA_CHECKS,
        'notice': '教学演练：只看决策，不执行导出。',
    },
    'TASK-DS-LOG-RETEST-001': {
        'version': 'm6-rules-v1-candidate',
        'type': 'structured_rules',
        'manual_required': False,
        'checks': RETEST_CHECKS,
        'notice': '新场景复测，按同等验收要求判定。',
    },
}


class Command(BaseCommand):
    help = 'Attach module-6 verification checks to the candidate task packages.'

    def add_arguments(self, parser):
        parser.add_argument('--catalog-version', default='v1-candidate')

    @transaction.atomic
    def handle(self, *args, **options):
        catalog = CatalogVersion.objects.filter(version=options['catalog_version']).first()
        if catalog is None:
            raise CommandError(f'目录版本 {options["version"]} 不存在，请先运行 seed_learning_map。')
        updated = 0
        for task_key, validator in VALIDATORS.items():
            task = TaskPackage.objects.filter(catalog=catalog, task_key=task_key).order_by('-version').first()
            if task is None:
                self.stdout.write(self.style.WARNING(f'跳过：目录中没有任务 {task_key}'))
                continue
            task.validator = validator
            task.save(update_fields=['validator', 'updated_at'])
            updated += 1
            self.stdout.write(f'{task_key}@{task.version} -> {validator["type"]} / {validator["version"]}')
        self.stdout.write(self.style.SUCCESS(f'已更新 {updated} 个任务的验证器；任务状态与审核状态未改动。'))
