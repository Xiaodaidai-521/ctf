from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIClient

from learning_knowledge.models import Material, MaterialChunk, ReviewAction
from learning_knowledge.policy import authorize
from learning_knowledge.review import inspection, new_revision, parse_candidate, register, transition
from learning_knowledge.services import read_evidence, search
from .helpers import setup_case


def metadata(text='原创教学草案。\n\n只在授权范围核查。'):
    return dict(title='教学依据', publisher='测试编审', source_version='test-1',
                source_date=date(2026, 10, 29), verified_at=date(2026, 10, 29),
                license_id='internal-review-only', attribution_text='Synthetic test author',
                reuse_scope='内部待审，不对外授权', applicability='仅合成任务', source_snapshot=text)


class ReviewTests(TestCase):
    def setUp(self):
        setup_case(self)
        self.revision = register(actor=self.teacher, catalog=self.task.catalog,
                                 material_class='lesson', tasks=[self.task], metadata=metadata())
        parse_candidate(revision_id=self.revision.pk, token=self.revision.ingestion_token)

    def act(self, action, actor=None, revision=None, key=None):
        revision = revision or self.revision
        return transition(actor=actor or self.teacher, material_id=revision.material.material_id,
                          expected_revision=revision.revision, action=action,
                          idempotency_key=key or f'{action}-{revision.revision}', reason='合成测试审阅')

    def publish(self, revision=None):
        self.act('submit', revision=revision)
        self.act('approve', actor=self.admin, revision=revision)
        return self.act('publish', revision=revision)

    def test_t3_01_independent_review_and_live_reviewer_duty(self):
        self.assertIsNone(authorize(self.revision.pk, self.scope))
        self.act('submit')
        with self.assertRaises(ValidationError):
            self.act('approve')
        self.act('approve', self.admin)
        self.admin.is_active = False
        self.admin.save()
        with self.assertRaises(ValidationError):
            self.act('publish')
        self.admin.is_active = True
        self.admin.save()
        self.act('publish')
        self.assertIsNotNone(authorize(self.revision.pk, self.scope))

    def test_revision_author_cannot_review_own_replacement(self):
        replacement = new_revision(actor=self.admin, material=self.revision.material,
                                   tasks=[self.task], metadata=metadata('替换草案'))
        parse_candidate(revision_id=replacement.pk, token=replacement.ingestion_token)
        self.act('submit', self.admin, replacement)
        with self.assertRaises(ValidationError):
            self.act('approve', self.admin, replacement)

    def test_action_idempotency_conflict_and_stale_revision(self):
        self.act('submit')
        self.act('submit')
        self.assertEqual(ReviewAction.objects.count(), 1)
        with self.assertRaises(ValidationError):
            self.act('approve', self.admin, key='submit-1')
        new_revision(actor=self.teacher, material=self.revision.material,
                     tasks=[self.task], metadata=metadata('新草案'))
        with self.assertRaises(ValidationError):
            self.act('approve', self.admin)

    def test_source_and_chunk_integrity_required_for_publish(self):
        self.act('submit')
        self.act('approve', self.admin)
        MaterialChunk.objects.filter(revision=self.revision).update(chunk_hash='0' * 64)
        with self.assertRaises(NotFound):
            self.act('publish')
        self.assertIsNone(authorize(self.revision.pk, self.scope))

    def test_t3_08_old_worker_cannot_replace_new_candidate(self):
        old_chunks = list(self.revision.chunks.values_list('pk', flat=True))
        replacement = new_revision(actor=self.teacher, material=self.revision.material,
                                   tasks=[self.task], metadata=metadata('新草案'))
        with self.assertRaises(ValidationError):
            parse_candidate(revision_id=self.revision.pk, token=self.revision.ingestion_token)
        parse_candidate(revision_id=replacement.pk, token=replacement.ingestion_token)
        self.assertEqual(list(self.revision.chunks.values_list('pk', flat=True)), old_chunks)

    def test_t3_08_failed_candidate_swap_preserves_published_revision(self):
        self.publish()
        replacement = new_revision(actor=self.teacher, material=self.revision.material,
                                   tasks=[self.task], metadata=metadata('新草案'))
        with patch('learning_knowledge.review.MaterialChunk.objects.bulk_create', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                parse_candidate(revision_id=replacement.pk, token=replacement.ingestion_token)
        self.assertIsNotNone(authorize(self.revision.pk, self.scope))
        self.assertFalse(replacement.chunks.exists())

    def test_t3_16_replacement_and_withdrawal_preserve_audit_not_old_access(self):
        self.publish()
        evidence = search(self.scope)['results'][0]
        replacement = new_revision(actor=self.teacher, material=self.revision.material,
                                   tasks=[self.task], metadata=metadata('替换依据'))
        parse_candidate(revision_id=replacement.pk, token=replacement.ingestion_token)
        self.publish(replacement)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.review_status, 'superseded')
        self.assertTrue(self.revision.chunks.exists())
        with self.assertRaises(NotFound):
            read_evidence(evidence['evidence_id'], self.student)
        self.assertEqual({c['material_revision'] for c in search(self.scope)['results']}, {2})
        self.act('withdraw', revision=replacement)
        self.assertEqual(search(self.scope)['results'], [])
        self.assertTrue(ReviewAction.objects.filter(revision=self.revision).exists())

    def test_management_preview_never_authorizes_student(self):
        with self.assertRaises(NotFound):
            inspection(self.revision, self.student)
        preview = inspection(self.revision, self.teacher)
        self.assertEqual(len(preview['chunks']), 2)
        self.assertEqual(preview['affected_task_count'], 1)
        self.assertEqual(search(self.scope)['results'], [])
        client = APIClient()
        client.force_authenticate(self.student)
        response = client.get(f'/api/teaching-knowledge/materials/{self.revision.material.material_id}/chunks/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_http_review_state_and_bounded_actions(self):
        client = APIClient()
        url = f'/api/teaching-knowledge/materials/{self.revision.material.material_id}/'
        for action, actor in [('submit', self.teacher), ('approve', self.admin), ('publish', self.teacher)]:
            client.force_authenticate(actor)
            response = client.post(url + action + '/', {
                'expected_revision': 1, 'idempotency_key': action, 'reason': '本地合成审阅',
            }, format='json')
            self.assertEqual(response.status_code, 200, response.data)
        client.force_authenticate(self.student)
        response = client.post(url + 'withdraw/', {
            'expected_revision': 1, 'idempotency_key': 'withdraw', 'reason': 'not allowed',
        }, format='json')
        self.assertEqual(response.status_code, 404)
        client.force_authenticate(self.teacher)
        response = client.post(url + 'withdraw/', {
            'expected_revision': 1, 'idempotency_key': 'x' * 65, 'reason': 'test',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIsNotNone(authorize(self.revision.pk, self.scope))

    def test_pending_candidate_license_cannot_be_published(self):
        self.revision.license_id = 'LicenseRef-Project-Internal-Pending'
        self.revision.save(update_fields=['license_id'])
        self.act('submit')
        self.act('approve', self.admin)
        with self.assertRaisesRegex(ValidationError, 'Candidate reuse permission is pending'):
            self.act('publish')
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.parse_status, 'completed')
        self.assertEqual(self.revision.review_status, 'approved')
        self.assertFalse(ReviewAction.objects.filter(revision=self.revision, action='publish').exists())
        self.assertIsNone(authorize(self.revision.pk, self.scope))

    def test_missing_provenance_registration_is_atomic(self):
        incomplete = metadata()
        del incomplete['license_id']
        with self.assertRaises(ValidationError):
            register(actor=self.teacher, catalog=self.task.catalog, material_class='lesson',
                     tasks=[self.task], metadata=incomplete)
        self.assertEqual(Material.objects.count(), 1)
