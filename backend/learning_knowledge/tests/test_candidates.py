"""M3-03 uses only synthetic rows in Django's isolated test database."""
import hashlib
import json
from collections import Counter
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from learning_map.models import (
    Capability, CatalogVersion, DataBasisCard, KnowledgePoint, TaskAttempt,
    TaskPackage, WSTGMapping,
)
from teaching_agent.models import HintCard, StudentAnalysis
from learning_knowledge import candidate_materials, review
from learning_knowledge.management.commands.import_candidate_materials import candidate_id, source_metadata
from learning_knowledge.models import (
    CourseGrant, Material, MaterialChunk, MaterialRevision, ReviewAction, TaskMaterial,
)
from learning_knowledge.policy import Scope, authorize, live_attempt
from learning_knowledge.services import search

COMMAND = 'import_candidate_materials'
COMMAND_MODULE = f'learning_knowledge.management.commands.{COMMAND}'
EXPECTED_TASKS = [
    ('TASK-DS-CUSTOMER-TABLE-001', '1.0.0-candidate', 12),
    ('TASK-NS-OBJECT-AUTH-001', '0.1.0-candidate', 12),
    ('TASK-DS-LOG-RETEST-001', '1.0.0-candidate', 3),
    ('TASK-NS-RETEST-001', '0.1.0-candidate', 3),
]


class CandidateImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user(username='synthetic-m3-importer', role='admin')
        cls.teacher = User.objects.create_user(username='synthetic-m3-reviewer', role='teacher')
        cls.student = User.objects.create_user(username='synthetic-m3-student', role='student')
        cls.catalog = CatalogVersion.objects.create(version='synthetic-m3-03', label='Synthetic fixture only')
        cls.other_catalog = CatalogVersion.objects.create(version='synthetic-m3-other', label='Synthetic other')
        CourseGrant.objects.create(user=cls.admin, catalog=cls.catalog, maintain_secrets=True)
        CourseGrant.objects.create(user=cls.teacher, catalog=cls.catalog, can_review=True)
        cls.tasks = []
        for index, (key, version, _) in enumerate(EXPECTED_TASKS):
            track = 'data' if key.startswith('TASK-DS-') else 'network'
            points = [KnowledgePoint.objects.create(
                catalog=cls.catalog, stable_id=f'SYN-KP-{index}-{number}',
                track=track, name='Synthetic knowledge point',
            ) for number in (1, 2)]
            capabilities = [Capability.objects.create(
                catalog=cls.catalog, stable_id=f'SYN-CAP-{index}-{number}', track=track,
                title='Synthetic capability', observable_objective='Synthetic fixture mapping',
                dimension='explain',
            ) for number in (1, 2)]
            capabilities[0].knowledge_points.set(points)
            capabilities[1].knowledge_points.set(points[:1])
            task = TaskPackage.objects.create(
                catalog=cls.catalog, task_key=key, version=version, title='Synthetic task',
                track=track, purpose='retest' if 'RETEST' in key else 'verification',
                execution_mode='readonly_decision' if track == 'data' else 'isolated_challenge',
                materials={'notice': 'Synthetic fixture: do not overwrite'},
                hints=[{'level': 1, 'body_ref': 'synthetic-only'}],
                validator={'version': 'synthetic-only'},
            )
            task.capabilities.set(capabilities)
            cls.tasks.append(task)

    def invoke(self, **overrides):
        output = StringIO()
        options = {'actor': self.admin.pk, 'catalog': self.catalog.version, 'stdout': output}
        options.update(overrides)
        call_command(COMMAND, **options)
        return output.getvalue()

    def snapshot(self, models):
        return {model._meta.label: list(model.objects.order_by('pk').values()) for model in models}

    def material_snapshot(self):
        return self.snapshot((Material, MaterialRevision, MaterialChunk, TaskMaterial, ReviewAction,
                              HintCard, StudentAnalysis))

    def authority_snapshot(self):
        return self.snapshot((
            get_user_model(), CourseGrant, CatalogVersion, TaskPackage, Capability, KnowledgePoint,
            TaskPackage.capabilities.through, Capability.knowledge_points.through,
            DataBasisCard, WSTGMapping, TaskAttempt,
        ))

    def assert_rejected_without_changes(self, message, **options):
        before = self.material_snapshot(), self.authority_snapshot()
        output = StringIO()
        with self.assertRaisesMessage(CommandError, message):
            self.invoke(stdout=output, **options)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual((self.material_snapshot(), self.authority_snapshot()), before)

    def transition(self, revision, action):
        actor = self.teacher if action == 'approve' else self.admin
        return review.transition(
            actor=actor, material_id=revision.material.material_id, expected_revision=revision.revision,
            action=action, idempotency_key=f'synthetic-{action}', reason='Synthetic review fixture only',
        )

    def publish(self, revision):
        # Synthetic review-state fixture only, not approval of the bundled drafts' real license.
        revision.license_id = 'LicenseRef-Synthetic-Test-Reviewed'
        revision.save(update_fields=['license_id'])
        for action in ('submit', 'approve', 'publish'):
            revision = self.transition(revision, action)
        return revision

    def test_task_versions_match_existing_seed_contract(self):
        fixture = Path(__file__).resolve().parents[2] / 'learning_map/fixtures/module1_candidate_v1.json'
        data = json.loads(fixture.read_text(encoding='utf-8'))
        expected = {(key, version) for key, version, _ in EXPECTED_TASKS}
        self.assertEqual({(task['task_key'], task['version']) for task in data['tasks']}, expected)
        self.assertEqual([(key, version, len(cards)) for key, version, cards in candidate_materials.TASKS], EXPECTED_TASKS)

    def test_source_register_lists_every_original_snapshot_hash(self):
        register = Path(__file__).resolve().parents[3] / 'docs/module3/candidate-register.md'
        document = register.read_text(encoding='utf-8')
        self.assertIn(candidate_materials.SOURCE_VERSION, document)
        self.assertIn(candidate_materials.SOURCE_DATE.isoformat(), document)
        for prefix, (_, _, cards) in zip(('DS', 'NS', 'DS-RETEST', 'NS-RETEST'), candidate_materials.TASKS):
            counts = Counter()
            for kind, title, text in cards:
                counts[kind] += 1
                slot = f'{prefix}/{kind}-{counts[kind]:02d}'
                digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
                row = f'| `{slot}` | {title} | `{digest}` |'
                self.assertEqual(document.count(row), 1, slot)

    def test_actor_and_catalog_are_explicitly_required(self):
        for options in ({}, {'actor': self.admin.pk}, {'catalog': self.catalog.version}):
            with self.subTest(options=options), self.assertRaises(CommandError):
                call_command(COMMAND, stdout=StringIO(), **options)
        self.assertEqual(Material.objects.count(), 0)

    def test_cli_rejects_non_integer_actor(self):
        with self.assertRaises(CommandError):
            call_command(COMMAND, '--actor', 'not-a-user-id', '--catalog', self.catalog.version)
        self.assertEqual(Material.objects.count(), 0)

    def test_unknown_actor_is_not_created(self):
        self.assert_rejected_without_changes('existing user', actor=999999)

    def test_unknown_catalog_is_not_created(self):
        self.assert_rejected_without_changes('existing catalog version', catalog='not-an-existing-version')

    def test_admin_without_grant_is_rejected(self):
        CourseGrant.objects.filter(user=self.admin).delete()
        self.assert_rejected_without_changes('maintain_secrets')

    def test_admin_without_secret_duty_is_rejected(self):
        CourseGrant.objects.filter(user=self.admin).update(can_review=True, maintain_secrets=False)
        self.assert_rejected_without_changes('maintain_secrets')

    def test_inactive_grant_is_rejected(self):
        CourseGrant.objects.filter(user=self.admin).update(active=False)
        self.assert_rejected_without_changes('maintain_secrets')

    def test_other_catalog_grant_is_not_authority(self):
        CourseGrant.objects.filter(user=self.admin).update(catalog=self.other_catalog)
        self.assert_rejected_without_changes('maintain_secrets')

    def test_teacher_even_with_secret_grant_is_rejected(self):
        CourseGrant.objects.filter(user=self.teacher).update(maintain_secrets=True)
        self.assert_rejected_without_changes('active admin', actor=self.teacher.pk)

    def test_student_even_with_full_grant_is_rejected(self):
        CourseGrant.objects.create(user=self.student, catalog=self.catalog, can_review=True, maintain_secrets=True)
        self.assert_rejected_without_changes('active admin', actor=self.student.pk)

    def test_staff_is_not_admin(self):
        get_user_model().objects.filter(pk=self.admin.pk).update(role='student', is_staff=True)
        self.assert_rejected_without_changes('active admin')

    def test_inactive_admin_is_rejected(self):
        get_user_model().objects.filter(pk=self.admin.pk).update(is_active=False)
        self.assert_rejected_without_changes('active admin')

    def test_superuser_still_needs_secret_grant(self):
        get_user_model().objects.filter(pk=self.admin.pk).update(role='student', is_superuser=True)
        CourseGrant.objects.filter(user=self.admin).delete()
        self.assert_rejected_without_changes('maintain_secrets')
        CourseGrant.objects.create(user=self.admin, catalog=self.catalog, maintain_secrets=True)
        self.assertIn('created=30, skipped=0', self.invoke())

    def test_missing_last_task_fails_whole_batch(self):
        self.tasks[-1].delete()
        self.assert_rejected_without_changes('Required task missing')

    def test_wrong_task_version_is_not_substituted(self):
        TaskPackage.objects.filter(pk=self.tasks[-1].pk).update(version='9.9.9-synthetic')
        self.assert_rejected_without_changes('Required task missing')

    def test_task_from_other_catalog_is_not_borrowed(self):
        TaskPackage.objects.filter(pk=self.tasks[-1].pk).update(catalog=self.other_catalog)
        self.assert_rejected_without_changes('Required task missing')

    def test_empty_capability_mapping_is_rejected(self):
        self.tasks[-1].capabilities.clear()
        self.assert_rejected_without_changes('no capability mapping')

    def test_missing_knowledge_mapping_is_rejected(self):
        self.tasks[-1].capabilities.first().knowledge_points.clear()
        self.assert_rejected_without_changes('knowledge mapping')

    def test_cross_catalog_capability_is_rejected(self):
        capability = self.tasks[-1].capabilities.first()
        Capability.objects.filter(pk=capability.pk).update(catalog=self.other_catalog)
        self.assert_rejected_without_changes('cross-catalog knowledge mapping')

    def test_cross_catalog_knowledge_point_is_rejected(self):
        point = self.tasks[-1].capabilities.first().knowledge_points.first()
        KnowledgePoint.objects.filter(pk=point.pk).update(catalog=self.other_catalog)
        self.assert_rejected_without_changes('cross-catalog knowledge mapping')

    def test_imports_exactly_30_drafts_with_hashes_and_live_mappings(self):
        before = self.authority_snapshot()
        registered_on = date(2026, 10, 30)
        with patch(f'{COMMAND_MODULE}.timezone.localdate', return_value=registered_on):
            output = self.invoke()
        self.assertIn('created=30, skipped=0', output)
        self.assertEqual(self.authority_snapshot(), before)
        self.assertEqual(Material.objects.count(), 30)
        self.assertEqual(MaterialRevision.objects.count(), 30)
        self.assertEqual(MaterialChunk.objects.count(), 30)
        self.assertEqual(TaskMaterial.objects.count(), 30)
        self.assertEqual(Counter(Material.objects.values_list('material_class', flat=True)), {
            'lesson': 16, 'hint': 8, 'student_analysis': 2, 'teacher_answer': 2, 'grading_secret': 2,
        })
        self.assertEqual(ReviewAction.objects.count(), 0)
        self.assertEqual(HintCard.objects.count(), 0)
        self.assertEqual(StudentAnalysis.objects.count(), 0)
        for task, (_, _, cards) in zip(self.tasks, candidate_materials.TASKS):
            counts = Counter()
            for kind, title, text in cards:
                counts[kind] += 1
                revision = MaterialRevision.objects.get(material__material_id=candidate_id(
                    self.catalog.version, task.task_key, task.version, kind, counts[kind],
                ))
                with self.subTest(task=task.task_key, kind=kind, ordinal=counts[kind]):
                    material = revision.material
                    self.assertEqual(material.owner_id, self.admin.pk)
                    self.assertEqual(revision.author_id, self.admin.pk)
                    self.assertEqual(material.catalog_id, self.catalog.pk)
                    self.assertEqual(material.source_type, 'teacher_authored')
                    self.assertIsNone(material.source_object_id)
                    self.assertEqual(material.published_scope, 'internal')
                    self.assertIsNone(material.revoked_at)
                    self.assertEqual(material.acl_version, 1)
                    self.assertEqual(material.hint_level, counts[kind] if kind == 'hint' else None)
                    self.assertEqual(revision.review_status, 'draft')
                    self.assertEqual(revision.parse_status, 'completed')
                    self.assertEqual(revision.revision, 1)
                    self.assertEqual(revision.title, title)
                    self.assertEqual(revision.source_snapshot, text)
                    self.assertEqual(revision.source_hash, hashlib.sha256(text.encode('utf-8')).hexdigest())
                    self.assertEqual(revision.source_version, candidate_materials.SOURCE_VERSION)
                    self.assertEqual(revision.source_date, candidate_materials.SOURCE_DATE)
                    self.assertEqual(revision.verified_at, registered_on)
                    self.assertIsNotNone(revision.created_at)
                    self.assertIsNotNone(material.created_at)
                    self.assertEqual(revision.license_id, 'LicenseRef-Project-Internal-Pending')
                    self.assertEqual(revision.source_url, '')
                    self.assertEqual(revision.license_url, '')
                    self.assertIn('项目内部待确认', revision.reuse_scope)
                    self.assertIn('原创待教师审核', revision.attribution_text)
                    self.assertIn(f'user_id={self.admin.pk}', revision.attribution_text)
                    self.assertIn('不表示法规现行性', revision.change_note)
                    self.assertIn(self.catalog.version, revision.applicability)
                    self.assertIn(f'{task.task_key}@{task.version}', revision.applicability)
                    if task.track == 'network':
                        self.assertIn('WSTG v4.2', revision.applicability)
                        self.assertIn('https://wstg.owasp.org/v4.2/', revision.applicability)
                        self.assertIn('非翻译转载', revision.applicability)
                    self.assertIsNone(revision.reviewer_id)
                    self.assertIsNone(revision.reviewed_at)
                    self.assertIsNone(revision.published_at)
                    self.assertEqual(revision.ingestion_token, material.ingestion_token)
                    binding = revision.bindings.get()
                    self.assertEqual(binding.task_id, task.pk)
                    self.assertEqual(set(binding.capability_ids), set(task.capabilities.values_list('stable_id', flat=True)))
                    self.assertEqual(set(binding.knowledge_point_ids), set(task.capabilities.values_list('knowledge_points__stable_id', flat=True)))
                    chunk = revision.chunks.get()
                    self.assertEqual((chunk.start, chunk.end), (0, len(text)))
                    self.assertEqual(chunk.chunk_hash, revision.source_hash)
                    self.assertEqual(chunk.locator, {'paragraph': 1})
                    self.assertEqual(chunk.heading_path, [title])
                    self.assertIsNone(chunk.embedding_id)

    def test_retest_cards_are_separate_lesson_only_materials(self):
        self.invoke()
        bindings = TaskMaterial.objects.filter(task__task_key__contains='RETEST')
        self.assertEqual(bindings.count(), 6)
        self.assertEqual(bindings.values('revision__material_id').distinct().count(), 6)
        self.assertEqual(set(bindings.values_list('revision__material__material_class', flat=True)), {'lesson'})
        for task in self.tasks[:2]:
            self.assertEqual(list(Material.objects.filter(
                revisions__bindings__task=task, material_class='hint',
            ).order_by('hint_level').values_list('hint_level', flat=True)), [1, 2, 3, 4])

    def test_success_output_does_not_disclose_card_bodies_or_titles(self):
        output = self.invoke()
        for _, _, cards in candidate_materials.TASKS:
            for _, title, text in cards:
                self.assertNotIn(title, output)
                self.assertNotIn(text, output)
        self.assertNotIn('SYNTHETIC-M3-', output)

    def test_drafts_are_unavailable_even_with_live_student_authority(self):
        self.invoke()
        CatalogVersion.objects.filter(pk=self.catalog.pk).update(status='published')
        TaskPackage.objects.filter(catalog=self.catalog).update(status='frozen', environment_available=True)
        CourseGrant.objects.create(user=self.student, catalog=self.catalog)
        for task in self.tasks:
            attempt = TaskAttempt.objects.create(
                student=self.student, task=task, catalog=self.catalog, task_version=task.version,
            )
            scope = Scope(self.student, attempt.attempt_id)
            self.assertEqual(live_attempt(scope).pk, attempt.pk)
            self.assertEqual(search(scope)['results'], [])
            for revision in MaterialRevision.objects.filter(bindings__task=task):
                self.assertIsNone(authorize(revision.pk, scope))

    def test_rerun_is_a_byte_for_byte_database_noop(self):
        self.invoke()
        before = self.material_snapshot(), self.authority_snapshot()
        with patch(f'{COMMAND_MODULE}.timezone.localdate', return_value=date(2027, 1, 1)):
            self.assertIn('created=0, skipped=30', self.invoke())
        self.assertEqual((self.material_snapshot(), self.authority_snapshot()), before)

    def test_rerun_with_another_actor_does_not_reassign_ownership(self):
        self.invoke()
        other = get_user_model().objects.create_user(username='synthetic-other-admin', role='admin')
        CourseGrant.objects.create(user=other, catalog=self.catalog, maintain_secrets=True)
        before = self.material_snapshot(), self.authority_snapshot()
        self.assertIn('created=0, skipped=30', self.invoke(actor=other.pk))
        self.assertEqual((self.material_snapshot(), self.authority_snapshot()), before)

    def test_rerun_rechecks_secret_grant_even_when_all_cards_exist(self):
        self.invoke()
        CourseGrant.objects.filter(user=self.admin).update(maintain_secrets=False)
        self.assert_rejected_without_changes('maintain_secrets')

    def test_rerun_preserves_reviews_new_revisions_and_static_cards(self):
        self.invoke()
        lessons = list(MaterialRevision.objects.filter(material__material_class='lesson').order_by('pk')[:4])
        self.transition(lessons[0], 'submit')
        self.transition(lessons[1], 'submit')
        self.transition(lessons[1], 'approve')
        published = self.publish(lessons[2])
        self.transition(self.publish(lessons[3]), 'withdraw')
        for kind in ('hint', 'student_analysis'):
            self.publish(MaterialRevision.objects.filter(material__material_class=kind).first())
        task = published.bindings.get().task
        revised = review.new_revision(
            actor=self.admin, material=published.material, tasks=[task],
            metadata=source_metadata(
                actor=self.admin, catalog=self.catalog, task=task,
                title='Synthetic reviewed edit', text='Synthetic changed content, not the bundle.',
                registered_on=date(2026, 10, 30),
            ),
        )
        review.parse_candidate(revision_id=revised.pk, token=revised.ingestion_token)
        self.publish(revised)
        published.refresh_from_db()
        self.assertEqual(published.review_status, 'superseded')
        before = self.material_snapshot(), self.authority_snapshot()
        self.assertIn('created=0, skipped=30', self.invoke())
        self.assertEqual((self.material_snapshot(), self.authority_snapshot()), before)

    def test_edited_bundle_does_not_overwrite_imported_materials(self):
        self.invoke()
        before = self.material_snapshot()
        changed = [(key, version, [(kind, 'Synthetic changed title', 'Synthetic changed body')
                                  for kind, _, _ in cards]) for key, version, cards in candidate_materials.TASKS]
        with patch.object(candidate_materials, 'TASKS', changed), patch.object(candidate_materials, 'SOURCE_VERSION', 'synthetic-next'):
            self.assertIn('created=0, skipped=30', self.invoke())
        self.assertEqual(self.material_snapshot(), before)

    def test_register_failure_rolls_back_previously_created_cards(self):
        real_register = review.register
        seen = []

        def fail_after_register(**kwargs):
            revision = real_register(**kwargs)
            seen.append(revision.pk)
            if len(seen) == 6:
                raise ValidationError('Synthetic registration fault')
            return revision

        with patch.object(review, 'register', side_effect=fail_after_register):
            self.assert_rejected_without_changes('transaction rolled back')
        self.assertEqual(len(seen), 6)

    def test_parse_failure_on_last_card_rolls_back_everything_without_leaking(self):
        real_parse = review.parse_candidate
        seen = []

        def fail_after_parse(**kwargs):
            revision = real_parse(**kwargs)
            seen.append(revision.pk)
            if len(seen) == 30:
                raise ValidationError('SYNTHETIC-SECRET-FAULT-DO-NOT-LOG')
            return revision

        with patch.object(review, 'parse_candidate', side_effect=fail_after_parse):
            self.assert_rejected_without_changes('Candidate import failed; transaction rolled back.')
        self.assertEqual(len(seen), 30)
        self.assertIn('created=30, skipped=0', self.invoke())

    def test_database_failure_is_atomic(self):
        real_parse = review.parse_candidate
        seen = []

        def database_failure(**kwargs):
            result = real_parse(**kwargs)
            seen.append(result.pk)
            if len(seen) == 4:
                raise IntegrityError('Synthetic unique constraint failure')
            return result

        with patch.object(review, 'parse_candidate', side_effect=database_failure):
            self.assert_rejected_without_changes('transaction rolled back')
        self.assertEqual(len(seen), 4)

    def test_identity_conflict_preserves_existing_rows_and_rolls_back_batch(self):
        task = self.tasks[-1]
        Material.objects.create(
            material_id=candidate_id(self.catalog.version, task.task_key, task.version, 'lesson', 3),
            catalog=self.other_catalog, material_class='lesson',
        )
        self.assert_rejected_without_changes('Candidate identity conflict')

    def test_partial_previous_import_is_resumed_without_touching_review(self):
        task = self.tasks[0]
        kind, title, text = candidate_materials.DATA[0]
        revision = review.register(
            actor=self.admin, catalog=self.catalog, material_class=kind, tasks=[task],
            metadata=source_metadata(actor=self.admin, catalog=self.catalog, task=task,
                                     title=title, text=text, registered_on=date(2026, 10, 29)),
        )
        material = revision.material
        material.material_id = candidate_id(self.catalog.version, task.task_key, task.version, kind, 1)
        material.save(update_fields=['material_id'])
        review.parse_candidate(revision_id=revision.pk, token=revision.ingestion_token)
        self.publish(revision)
        saved_material = Material.objects.filter(pk=material.pk).values().get()
        saved_revision = MaterialRevision.objects.filter(pk=revision.pk).values().get()
        with patch.object(review, 'parse_candidate', side_effect=ValidationError('Synthetic fault')):
            self.assert_rejected_without_changes('transaction rolled back')
        self.assertIn('created=29, skipped=1', self.invoke())
        self.assertEqual(Material.objects.filter(pk=material.pk).values().get(), saved_material)
        self.assertEqual(MaterialRevision.objects.filter(pk=revision.pk).values().get(), saved_revision)
        self.assertEqual(Material.objects.count(), 30)
