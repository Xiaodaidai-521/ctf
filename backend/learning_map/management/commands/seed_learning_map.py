import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from learning_map import constants
from learning_map.models import (
    Capability,
    CatalogVersion,
    DataBasisCard,
    DeliveryRegisterItem,
    DiagnosticQuestion,
    KnowledgePoint,
    LegacyLabelMapping,
    TaskPackage,
    WSTGMapping,
)


DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures' / 'module1_candidate_v1.json'


class Command(BaseCommand):
    help = 'Load the module-1 candidate catalog, diagnostic questions, task packages and delivery register.'

    def add_arguments(self, parser):
        parser.add_argument('--fixture', default=str(DEFAULT_FIXTURE))
        parser.add_argument('--skip-legacy-inspect', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        fixture_path = Path(options['fixture'])
        if not fixture_path.exists():
            raise CommandError(f'fixture not found: {fixture_path}')
        data = json.loads(fixture_path.read_text(encoding='utf-8'))
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('dry-run: no rows written'))
            return

        catalog_data = data['catalog']
        catalog, created = CatalogVersion.objects.get_or_create(
            version=catalog_data['version'],
            defaults={
                'label': catalog_data['label'],
                'status': catalog_data.get('status', constants.CATALOG_STATUS_CANDIDATE),
                'rule_version': catalog_data.get('rule_version', constants.RULE_VERSION),
                'notes': catalog_data.get('notes', ''),
            },
        )
        if not created:
            catalog.label = catalog_data['label']
            catalog.notes = catalog_data.get('notes', catalog.notes)
            if catalog.status == constants.CATALOG_STATUS_CANDIDATE:
                catalog.rule_version = catalog_data.get('rule_version', catalog.rule_version)
            catalog.save(update_fields=['label', 'notes', 'rule_version', 'updated_at'])

        knowledge_points = {}
        for item in data.get('knowledge_points', []):
            knowledge_point, _ = KnowledgePoint.objects.update_or_create(
                catalog=catalog,
                stable_id=item['stable_id'],
                defaults={
                    'track': item['track'],
                    'name': item['name'],
                    'description': item.get('description', ''),
                    'sort_order': item.get('sort_order', 0),
                },
            )
            knowledge_points[item['stable_id']] = (knowledge_point, item.get('prerequisite_ids', []))

        capabilities = {}
        for item in data.get('capabilities', []):
            capability, _ = Capability.objects.update_or_create(
                catalog=catalog,
                stable_id=item['stable_id'],
                defaults={
                    'track': item['track'],
                    'title': item['title'],
                    'observable_objective': item['observable_objective'],
                    'dimension': item['dimension'],
                    'difficulty': item.get('difficulty', 1),
                    'source_refs': item.get('source_refs', []),
                    'status': item.get('status', constants.CAPABILITY_STATUS_TO_BUILD),
                    'course_order': item.get('course_order', 0),
                },
            )
            capability.knowledge_points.set([
                knowledge_points[point_id][0]
                for point_id in item.get('knowledge_point_ids', [])
                if point_id in knowledge_points
            ])
            capabilities[item['stable_id']] = (capability, item.get('prerequisite_ids', []))

        for stable_id, (capability, prerequisite_ids) in capabilities.items():
            capability.prerequisites.set([
                capabilities[prerequisite_id][0]
                for prerequisite_id in prerequisite_ids
                if prerequisite_id in capabilities
            ])
        for stable_id, (knowledge_point, prerequisite_ids) in knowledge_points.items():
            knowledge_point.prerequisites.set([
                knowledge_points[prerequisite_id][0]
                for prerequisite_id in prerequisite_ids
                if prerequisite_id in knowledge_points
            ])

        for item in data.get('legacy_labels', []):
            capability = capabilities.get(item.get('capability_id')) if item.get('capability_id') else None
            knowledge_point = knowledge_points.get(item.get('knowledge_point_id')) if item.get('knowledge_point_id') else None
            # Never overwrite a mapping a course owner has already reviewed.
            LegacyLabelMapping.objects.get_or_create(
                catalog=catalog,
                source_system=item['source_system'],
                source_label=item['source_label'],
                source_ref=item.get('source_ref', ''),
                defaults={
                    'capability': capability[0] if capability else None,
                    'knowledge_point': knowledge_point[0] if knowledge_point else None,
                    'mapping_status': item.get('mapping_status', constants.MAPPING_UNMAPPED),
                    'note': item.get('note', ''),
                },
            )

        for item in data.get('wstg_mappings', []):
            capability = capabilities.get(item.get('capability_id'))
            WSTGMapping.objects.get_or_create(
                catalog=catalog,
                scenario_id=item['scenario_id'],
                defaults={
                    'wstg_version': item.get('wstg_version', '4.2'),
                    'scenario_title': item['scenario_title'],
                    'capability': capability[0] if capability else None,
                    'prerequisite_ids': item.get('prerequisite_ids', []),
                    'difficulty': item.get('difficulty', 1),
                    'exercise_ref': item.get('exercise_ref', ''),
                    'acceptance_evidence': item.get('acceptance_evidence', ''),
                    'status': item.get('status', 'draft'),
                    'notes': item.get('notes', ''),
                },
            )

        for item in data.get('basis_cards', []):
            capability = capabilities.get(item.get('capability_id'))
            DataBasisCard.objects.get_or_create(
                catalog=catalog,
                card_id=item['card_id'],
                defaults={
                    'capability': capability[0] if capability else None,
                    'source_title': item['source_title'],
                    'source_clause': item.get('source_clause', ''),
                    'source_version': item.get('source_version', ''),
                    'source_url': item.get('source_url', ''),
                    'applicable_facts': item.get('applicable_facts', ''),
                    'classification_conclusion': item.get('classification_conclusion', ''),
                    'uncertainties': item.get('uncertainties', ''),
                    'protection_measures': item.get('protection_measures', ''),
                    'scoring_evidence': item.get('scoring_evidence', ''),
                    'status': item.get('status', 'draft'),
                    'notes': item.get('notes', ''),
                },
            )

        for item in data.get('diagnostic_questions', []):
            capability = capabilities.get(item['capability_id'])
            if not capability:
                continue
            question, question_created = DiagnosticQuestion.objects.update_or_create(
                catalog=catalog,
                question_key=item['question_key'],
                version=item.get('version', '1.0.0'),
                defaults={
                    'track': item['track'],
                    'capability': capability[0],
                    'dimension': item['dimension'],
                    'prompt': item['prompt'],
                    'options': item.get('options', []),
                    'correct_options': item.get('correct_options', []),
                    'points': item.get('points', 1),
                    'sort_order': item.get('sort_order', 0),
                },
            )
            if question_created:
                question.status = item.get('status', 'draft')
                question.save(update_fields=['status'])

        for item in data.get('tasks', []):
            task, task_created = TaskPackage.objects.update_or_create(
                task_key=item['task_key'],
                version=item['version'],
                defaults={
                    'catalog': catalog,
                    'title': item['title'],
                    'track': item['track'],
                    'purpose': item['purpose'],
                    'execution_mode': item['execution_mode'],
                    'materials': item.get('materials', {}),
                    'hints': item.get('hints', []),
                    'student_solution_ref': item.get('student_solution_ref', ''),
                    'validator': item.get('validator', {}),
                    'acceptance': item.get('acceptance', {}),
                    'retest_task_keys': item.get('retest_task_keys', []),
                    'environment_available': item.get('environment_available', True),
                    'requires_milestone_i': item.get('requires_milestone_i', False),
                    'course_order': item.get('course_order', 0),
                },
            )
            if task_created:
                task.status = item.get('status', constants.TASK_STATUS_DRAFT)
                task.save(update_fields=['status'])
            task.capabilities.set([
                capabilities[capability_id][0]
                for capability_id in item.get('capability_ids', [])
                if capability_id in capabilities
            ])
            task.prerequisite_capabilities.set([
                capabilities[capability_id][0]
                for capability_id in item.get('prerequisite_capability_ids', [])
                if capability_id in capabilities
            ])

        for item in data.get('delivery_items', []):
            DeliveryRegisterItem.objects.get_or_create(
                delivery_no=item['delivery_no'],
                defaults={
                    'catalog': catalog,
                    'title': item['title'],
                    'required_contents': item.get('required_contents', ''),
                    'version': item.get('version', ''),
                    'status': item.get('status', constants.DELIVERY_PENDING),
                    'open_issues': item.get('open_issues', ''),
                    'notes': item.get('notes', ''),
                },
            )

        if not options['skip_legacy_inspect']:
            self._inspect_legacy(catalog)

        self.stdout.write(self.style.SUCCESS(
            f'catalog {catalog.version}: '
            f'{catalog.capabilities.count()} capabilities, '
            f'{catalog.knowledge_points.count()} knowledge points, '
            f'{catalog.tasks.count()} tasks, '
            f'{catalog.diagnostic_questions.count()} diagnostic questions, '
            f'{catalog.legacy_mappings.count()} legacy mappings'
        ))

    def _inspect_legacy(self, catalog):
        """Register unknown existing labels as unmapped, never as guessed mappings."""

        from challenges.models import Challenge
        from learning_paths.models import KnowledgeConcept, LearningPath, PathModule

        existing = set(
            LegacyLabelMapping.objects.filter(catalog=catalog)
            .values_list('source_system', 'source_label')
        )
        created = 0
        sources = [
            ('learning_path', LearningPath, 'title'),
            ('path_module', PathModule, 'title'),
            ('challenge', Challenge, 'title'),
            ('knowledge_concept', KnowledgeConcept, 'name'),
        ]
        for source_system, model, label_field in sources:
            for obj in model.objects.all().only('id', label_field):
                label = getattr(obj, label_field)
                if (source_system, label) in existing:
                    continue
                LegacyLabelMapping.objects.create(
                    catalog=catalog,
                    source_system=source_system,
                    source_label=label,
                    source_ref=f'id={obj.id}',
                    mapping_status=constants.MAPPING_UNMAPPED,
                    note='现有数据自动登记；待课程负责人逐项确认映射，确认前不计入能力统计。',
                )
                existing.add((source_system, label))
                created += 1
        if created:
            self.stdout.write(self.style.WARNING(f'inspected legacy labels: added {created} unmapped rows'))
