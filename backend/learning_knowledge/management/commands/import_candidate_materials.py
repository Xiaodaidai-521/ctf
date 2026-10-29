"""Register the bundled original drafts, never grant, review or publish them."""
import json
from collections import Counter
from uuid import NAMESPACE_URL, uuid5

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from learning_map.models import CatalogVersion, TaskPackage
from learning_knowledge import candidate_materials, review
from learning_knowledge.models import Material
from learning_knowledge.policy import can_manage


def candidate_id(catalog_version, task_key, task_version, material_class, ordinal):
    # Stable slots, NOT content hashes: editing a draft must not bypass its review.
    # Do not renumber/reorder existing cards within a class in candidate_materials.
    key = json.dumps(
        ['m3-original-candidate', catalog_version, task_key, task_version, material_class, ordinal],
        ensure_ascii=False, separators=(',', ':'),
    )
    return uuid5(NAMESPACE_URL, key)


def source_metadata(*, actor, catalog, task, title, text, registered_on):
    applicability = (
        f'仅适用于目录 {catalog.version} 的 {task.task_key}@{task.version}；'
        '知识点与能力映射取自该任务当前目录关系，仅为候选映射，待教师逐卡复核。'
        '只用于合成案例教学，不代表真实学生成果、法规原文或业务合规结论。'
    )
    if task.task_key.startswith('TASK-NS-'):
        applicability += candidate_materials.WSTG_REFERENCE
    else:
        applicability += '仅做只读风险决策回放；执行、交付、结算均未开展。'
    if 'RETEST' in task.task_key:
        applicability += '复测仅预置基础材料，不导入复测提示或解析，不预填通过成绩。'
    return {
        'title': title,
        'publisher': '项目内部原创候选素材（待教师审核）',
        'source_version': candidate_materials.SOURCE_VERSION,
        'source_date': candidate_materials.SOURCE_DATE,
        'verified_at': registered_on,
        'source_url': '',
        'license_id': candidate_materials.LICENSE_ID,
        'license_url': '',
        'attribution_text': (
            f'原创待教师审核；登记责任人：{actor.get_username()}（user_id={actor.pk}）。'
            '来源：backend/learning_knowledge/candidate_materials.py；'
            '登记人不等同于已签署的内容作者或审核人；著作权归属及复用许可待项目确认。'
            '非法规原文，非 WSTG 翻译转载，不声明 CC 授权。'
        ),
        'reuse_scope': '项目内部待确认；仅限指定课程的候选审阅，不得据此对外转载或发布。',
        'applicability': applicability,
        'source_snapshot': text,
        'change_note': (
            'M3-03 原创候选初次登记；source_date 为此候选版本登记日期；'
            'verified_at 仅记录本地快照登记日期，不表示法规现行性、外部来源或许可已核验。'
            '未提交审核、未审批、未发布。'
        ),
    }


class Command(BaseCommand):
    help = 'Import 30 original candidate cards as draft/internal into an existing catalog.'

    def add_arguments(self, parser):
        parser.add_argument('--actor', type=int, required=True, help='Existing responsible user primary key.')
        parser.add_argument('--catalog', required=True, help='Exact existing CatalogVersion.version (not its primary key).')

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                created, skipped = self._import(options['actor'], options['catalog'])
        except (APIException, DatabaseError) as exc:
            # Do not expose candidate bodies, especially grading_secret, in CLI logs.
            raise CommandError('Candidate import failed; transaction rolled back.') from exc
        self.stdout.write(self.style.SUCCESS(
            f'Candidate import: created={created}, skipped={skipped}; '
            'new cards=draft/internal; existing cards unchanged.'
        ))

    def _import(self, actor_id, catalog_version):
        User = get_user_model()
        try:
            actor = User.objects.get(pk=actor_id)
        except (User.DoesNotExist, ValueError, TypeError):
            raise CommandError('--actor must identify an existing user.') from None
        try:
            # Serialize imports into the same catalog on row-locking databases.
            # The unique deterministic material_id also prevents duplicate inserts.
            catalog = CatalogVersion.objects.select_for_update().get(version=catalog_version)
        except CatalogVersion.DoesNotExist:
            raise CommandError('--catalog must identify an existing catalog version.') from None

        # Check the entire batch even on a no-op rerun; never silently omit secrets.
        for kind in {card[0] for _, _, cards in candidate_materials.TASKS for card in cards}:
            if not can_manage(actor, Material(catalog=catalog, material_class=kind)):
                raise CommandError(
                    'Import requires an active admin and an existing active '
                    'maintain_secrets CourseGrant for the selected catalog; no grants were changed.'
                )

        tasks = []
        for task_key, version, cards in candidate_materials.TASKS:
            try:
                task = TaskPackage.objects.select_for_update().prefetch_related(
                    'capabilities__knowledge_points',
                ).get(catalog=catalog, task_key=task_key, version=version)
            except TaskPackage.DoesNotExist:
                raise CommandError(f'Required task missing from selected catalog: {task_key}@{version}.') from None
            capabilities = list(task.capabilities.all())
            if not capabilities:
                raise CommandError(f'Task has no capability mapping: {task_key}@{version}.')
            for capability in capabilities:
                points = list(capability.knowledge_points.all())
                if (capability.catalog_id != catalog.pk or not points
                        or any(point.catalog_id != catalog.pk for point in points)):
                    raise CommandError(f'Task has missing or cross-catalog knowledge mapping: {task_key}@{version}.')
            tasks.append((task, cards))

        created = skipped = 0
        registered_on = timezone.localdate()
        for task, cards in tasks:
            ordinals = Counter()
            for kind, title, text in cards:
                ordinals[kind] += 1
                ordinal = ordinals[kind]
                level = ordinal if kind == 'hint' else None
                material_id = candidate_id(catalog.version, task.task_key, task.version, kind, ordinal)
                existing = Material.objects.filter(material_id=material_id).first()
                if existing:
                    if (existing.catalog_id != catalog.pk or existing.material_class != kind
                            or existing.hint_level != level or existing.source_type != 'teacher_authored'
                            or not existing.revisions.exists()):
                        raise CommandError('Candidate identity conflict; transaction rolled back, inspect existing records.')
                    # Preserve ALL existing revisions, mappings, chunks, tokens and review results.
                    skipped += 1
                    continue
                revision = review.register(
                    actor=actor, catalog=catalog, material_class=kind, hint_level=level,
                    tasks=[task], source_type='teacher_authored',
                    metadata=source_metadata(
                        actor=actor, catalog=catalog, task=task, title=title, text=text,
                        registered_on=registered_on,
                    ),
                )
                material = revision.material
                material.material_id = material_id
                material.save(update_fields=['material_id'])
                review.parse_candidate(revision_id=revision.pk, token=revision.ingestion_token)
                created += 1
        return created, skipped
