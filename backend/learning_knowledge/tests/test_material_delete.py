"""Separate HTTP regression suite for full-material soft deletion."""
from unittest.mock import patch
from uuid import uuid4

from django.db import OperationalError
from django.test import TestCase
from rest_framework.exceptions import NotFound
from rest_framework.test import APIClient

from learning_knowledge.models import CourseGrant, Evidence, Material, MaterialRevision, ReviewAction
from learning_knowledge.policy import authorize, material_ref, task_policy_stamp
from learning_knowledge.review import new_revision, parse_candidate, transition
from learning_knowledge.services import search
from learning_map.models import CatalogVersion
from teaching_agent.models import HintCard, StudentAnalysis
from users.models import CTFUser
from .helpers import material, setup_case
from .test_review import metadata


class MaterialDeleteTests(TestCase):
    def setUp(self):
        setup_case(self)
        self.revision = material(self, text='Synthetic protected source; retain only in audit history.')
        self.client = APIClient()
        self.root = '/api/teaching-knowledge/'
        self.url = self.material_url(self.revision)

    def material_url(self, revision):
        return f'{self.root}materials/{revision.material.material_id}/'

    def payload(self, **overrides):
        return {'expected_revision': 1, 'reason': 'Remove obsolete teaching material.',
                'idempotency_key': 'delete-one', **overrides}

    def delete(self, actor=None, revision=None, **overrides):
        self.client.force_authenticate(actor or self.teacher)
        return self.client.delete(self.material_url(revision) if revision else self.url,
                                  self.payload(**overrides), format='json')

    def assert_private(self, response):
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        # CORS middleware may additionally vary on Origin.
        self.assertTrue({'authorization', 'cookie'}.issubset(
            {value.strip().lower() for value in response['Vary'].split(',')}))
        self.assertNotIn(self.revision.source_snapshot, str(response.data))

    def assert_unchanged(self):
        self.revision.refresh_from_db()
        self.revision.material.refresh_from_db()
        self.assertEqual(self.revision.review_status, 'published')
        self.assertEqual(self.revision.material.published_scope, 'learner')
        self.assertEqual(self.revision.material.acl_version, 1)
        self.assertIsNone(self.revision.material.revoked_at)
        self.assertFalse(ReviewAction.objects.filter(action='delete', revision=self.revision).exists())

    def test_actual_delete_url_teacher_and_response_contract(self):
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {'revision': 1, 'review_status': 'withdrawn', 'acl_version': 2})
        self.assert_private(response)
        action = ReviewAction.objects.get(action='delete')
        self.assertEqual(action.actor, self.teacher)
        self.assertEqual(action.revision, self.revision)
        self.assertEqual(action.idempotency_key, 'delete-one')
        self.assertEqual(action.reason, self.payload()['reason'])
        self.assertEqual(action.acl_version, 2)

    def test_same_course_teacher_need_not_own_material(self):
        reviewer = CTFUser.objects.create_user(username='delete-reviewer', role='teacher')
        CourseGrant.objects.create(user=reviewer, catalog=self.task.catalog, can_review=True)
        response = self.delete(actor=reviewer)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ReviewAction.objects.get(action='delete').actor, reviewer)

    def test_admin_can_delete_nonsecret_without_course_grant(self):
        self.assertFalse(CourseGrant.objects.filter(user=self.admin).exists())
        response = self.delete(actor=self.admin)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ReviewAction.objects.get(action='delete').actor, self.admin)

    def test_superuser_uses_existing_admin_authority(self):
        self.other.is_superuser = True
        self.other.save(update_fields=['is_superuser'])
        response = self.delete(actor=self.other)
        self.assertEqual(response.status_code, 200, response.data)

    def test_anonymous_delete_is_denied(self):
        response = self.client.delete(self.url, self.payload(), format='json')
        # Existing SessionAuthentication is first, so unauthenticated failures are 403.
        self.assertEqual(response.status_code, 403)
        self.assert_private(response)
        self.assert_unchanged()

    def test_student_and_staff_review_grant_do_not_authorize_delete(self):
        for staff in (False, True):
            with self.subTest(staff=staff):
                self.student.is_staff = staff
                self.student.save(update_fields=['is_staff'])
                CourseGrant.objects.filter(user=self.student).update(can_review=True, maintain_secrets=True)
                response = self.delete(actor=self.student)
                self.assertEqual(response.status_code, 404)
                self.assert_private(response)
        self.assert_unchanged()

    def test_teacher_requires_active_review_grant(self):
        for values in ({'can_review': False}, {'active': False, 'can_review': True}):
            with self.subTest(values=values):
                CourseGrant.objects.filter(user=self.teacher).update(**values)
                response = self.delete()
                self.assertEqual(response.status_code, 404)
                self.assert_private(response)
        self.assert_unchanged()

    def test_review_grant_for_another_catalog_does_not_authorize_delete(self):
        CourseGrant.objects.filter(user=self.teacher).delete()
        catalog = CatalogVersion.objects.create(version='delete-other-course', label='Other course')
        CourseGrant.objects.create(user=self.teacher, catalog=catalog, can_review=True)
        response = self.delete()
        self.assertEqual(response.status_code, 404)
        self.assert_unchanged()

    def test_inactive_teacher_and_admin_are_denied(self):
        for actor in (self.teacher, self.admin):
            with self.subTest(role=actor.role):
                actor.is_active = False
                actor.save(update_fields=['is_active'])
                response = self.delete(actor=actor)
                self.assertEqual(response.status_code, 404)
                self.assert_private(response)
        self.assert_unchanged()

    def test_unknown_id_has_same_not_found_boundary_as_unauthorized(self):
        denied = self.delete(actor=self.student)
        self.client.force_authenticate(self.teacher)
        unknown = self.client.delete(f'{self.root}materials/{uuid4()}/', self.payload(), format='json')
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.data, denied.data)
        self.assert_private(unknown)
        self.assert_unchanged()

    def test_unknown_revision_is_not_found_without_effects(self):
        response = self.delete(expected_revision=99)
        self.assertEqual(response.status_code, 404)
        self.assert_unchanged()

    def test_grading_secret_requires_admin_and_active_same_course_secret_grant(self):
        secret = material(self, 'grading_secret', text='Synthetic grading secret.')
        CourseGrant.objects.filter(user=self.teacher).update(maintain_secrets=True)
        for actor in (self.teacher, self.admin):
            with self.subTest(role=actor.role):
                response = self.delete(actor=actor, revision=secret)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(secret.source_snapshot, str(response.data))
        grant = CourseGrant.objects.create(user=self.admin, catalog=self.task.catalog, can_review=True)
        response = self.delete(actor=self.admin, revision=secret)
        self.assertEqual(response.status_code, 404)
        grant.maintain_secrets = True
        grant.active = False
        grant.save()
        self.assertEqual(self.delete(actor=self.admin, revision=secret).status_code, 404)
        grant.active = True
        grant.can_review = False  # Secret maintenance is separate from normal review duty.
        grant.save()
        response = self.delete(actor=self.admin, revision=secret)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn(secret.source_snapshot, str(response.data))
        self.assert_unchanged()

    def test_secret_maintenance_grant_for_another_course_is_insufficient(self):
        secret = material(self, 'grading_secret')
        catalog = CatalogVersion.objects.create(version='delete-secret-other-course', label='Other course')
        CourseGrant.objects.create(user=self.admin, catalog=catalog, maintain_secrets=True)
        self.assertEqual(self.delete(actor=self.admin, revision=secret).status_code, 404)
        self.assert_unchanged()

    def test_request_body_is_strict_bounded_and_required(self):
        invalid = [
            {}, [],
            self.payload(expected_revision=0), self.payload(expected_revision='bad'),
            self.payload(reason=''), self.payload(reason='   '), self.payload(reason='x' * 501),
            self.payload(idempotency_key=''), self.payload(idempotency_key='x' * 65),
            self.payload(catalog_version=self.task.catalog.version),
            self.payload(published_scope='learner'), self.payload(action='withdraw'),
        ]
        self.client.force_authenticate(self.teacher)
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.client.delete(self.url, payload, format='json')
                self.assertEqual(response.status_code, 400, response.data)
                self.assert_private(response)
        self.assert_unchanged()

    def test_query_scope_is_rejected_and_new_detail_route_is_delete_only(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.delete(self.url + '?catalog_version=other', self.payload(), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.url, self.payload(), format='json').status_code, 405)
        self.assert_unchanged()

    def test_stale_known_revision_cannot_delete_newer_draft(self):
        replacement = new_revision(actor=self.teacher, material=self.revision.material,
                                   tasks=[self.task], metadata=metadata('Replacement draft.'))
        response = self.delete()
        self.assertEqual(response.status_code, 400, response.data)
        self.assert_unchanged()
        self.assertEqual(replacement.review_status, 'draft')
        response = self.delete(expected_revision=2)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['revision'], 2)
        self.assertEqual(set(MaterialRevision.objects.values_list('review_status', flat=True)), {'withdrawn'})

    def test_identical_retry_is_idempotent_without_second_acl_increment(self):
        first = self.delete()
        self.revision.material.refresh_from_db()
        revoked_at = self.revision.material.revoked_at
        token = self.revision.material.ingestion_token
        repeated = self.delete()
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(repeated.data, first.data)
        self.revision.material.refresh_from_db()
        self.assertEqual(self.revision.material.revoked_at, revoked_at)
        self.assertEqual(self.revision.material.ingestion_token, token)
        self.assertEqual(ReviewAction.objects.count(), 1)

    def test_retry_conflicts_include_actor_reason_and_existing_review_action(self):
        self.assertEqual(self.delete().status_code, 200)
        self.assertEqual(self.delete(reason='Different reason.').status_code, 400)
        self.assertEqual(self.delete(actor=self.admin).status_code, 400)
        self.assertEqual(self.delete(idempotency_key='new-delete').status_code, 404)
        draft = material(self, status='draft')
        transition(actor=self.teacher, material_id=draft.material.material_id, expected_revision=1,
                   action='submit', idempotency_key='delete-one', reason=self.payload()['reason'])
        self.assertEqual(self.delete(revision=draft).status_code, 400)
        self.assertEqual(ReviewAction.objects.filter(action='delete').count(), 1)
        draft.material.refresh_from_db()
        self.assertIsNone(draft.material.revoked_at)

    def test_retry_rechecks_live_course_authorization(self):
        self.assertEqual(self.delete().status_code, 200)
        CourseGrant.objects.filter(user=self.teacher).update(active=False)
        response = self.delete()
        self.assertEqual(response.status_code, 404)
        self.assert_private(response)
        self.assertEqual(ReviewAction.objects.count(), 1)

    def test_soft_delete_hides_management_and_revokes_cached_learner_evidence(self):
        evidence = search(self.scope)['results'][0]
        evidence_count = Evidence.objects.count()
        snapshot = self.revision.source_snapshot
        chunks = list(self.revision.chunks.values())
        bindings = list(self.revision.bindings.values())
        before_stamp = task_policy_stamp(self.task)
        task_values = self.task.__class__.objects.filter(pk=self.task.pk).values().get()
        catalog_values = CatalogVersion.objects.filter(pk=self.task.catalog_id).values().get()
        self.assertEqual(self.delete().status_code, 200)
        self.revision.refresh_from_db()
        self.revision.material.refresh_from_db()
        self.assertEqual(self.revision.material.published_scope, 'deleted')
        self.assertIsNotNone(self.revision.material.revoked_at)
        self.assertEqual(self.revision.source_snapshot, snapshot)
        self.assertEqual(list(self.revision.chunks.values()), chunks)
        self.assertEqual(list(self.revision.bindings.values()), bindings)
        self.assertEqual(Evidence.objects.count(), evidence_count)
        self.assertTrue(Material.objects.filter(pk=self.revision.material_id).exists())
        self.assertNotEqual(before_stamp, task_policy_stamp(self.task))
        self.assertIsNone(authorize(self.revision.pk, self.scope))
        for actor in (self.teacher, self.admin):
            self.client.force_authenticate(actor)
            for path in ('materials/', 'material-search/?q=Synthetic'):
                self.assertEqual(self.client.get(self.root + path).data['results'], [])
            response = self.client.get(self.url + 'chunks/')
            self.assertEqual(response.status_code, 404)
            self.assert_private(response)
        self.client.force_authenticate(self.student)
        for suffix in ('', 'download/'):
            response = self.client.get(f'/api/learning-knowledge/evidence/{evidence["evidence_id"]}/' + suffix)
            self.assertEqual(response.status_code, 404)
            self.assert_private(response)
        response = self.client.post('/api/learning-knowledge/search/', {
            'attempt_id': str(self.attempt.attempt_id), 'request_id': 'after-delete',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['results'], [])
        self.assertEqual(self.task.__class__.objects.filter(pk=self.task.pk).values().get(), task_values)
        self.assertEqual(CatalogVersion.objects.filter(pk=self.task.catalog_id).values().get(), catalog_values)

    def test_delete_all_revisions_deactivates_all_hint_and_analysis_cards(self):
        for kind, level in (('hint', 1), ('student_analysis', None)):
            with self.subTest(kind=kind):
                original = material(self, kind, level=level)
                replacement = new_revision(actor=self.teacher, material=original.material,
                                           tasks=[self.task], metadata=metadata('Replacement candidate.'))
                refs = [material_ref(revision) for revision in (original, replacement)]
                for index, ref in enumerate(refs):
                    if kind == 'hint':
                        HintCard.objects.create(task=self.task, level=1, version=f'delete-{index}',
                                                title='Direction', content='Preserved hint.', material_ref=ref)
                    else:
                        StudentAnalysis.objects.create(task=self.task, version=f'delete-{index}',
                                                       title='Analysis', content='Preserved analysis.', content_ref=ref)
                response = self.delete(revision=replacement, expected_revision=2)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(list(original.material.revisions.values_list('review_status', flat=True)),
                                 ['withdrawn', 'withdrawn'])
                model, field = (HintCard, 'material_ref') if kind == 'hint' else (StudentAnalysis, 'content_ref')
                cards = model.objects.filter(**{f'{field}__in': refs})
                self.assertEqual(cards.count(), 2)
                self.assertFalse(cards.filter(is_active=True).exists())

    def test_deleted_material_cannot_be_revised_republished_or_reparsed(self):
        draft = material(self, status='draft')
        # Existing submit retry must not report success after deletion either.
        transition(actor=self.teacher, material_id=draft.material.material_id, expected_revision=1,
                   action='submit', idempotency_key='submit-before-delete', reason='Review candidate.')
        self.assertEqual(self.delete(revision=draft).status_code, 200)
        for action in ('submit', 'approve', 'publish', 'withdraw'):
            response = self.client.post(self.material_url(draft) + action + '/', {
                'expected_revision': 1, 'reason': 'Review candidate.',
                'idempotency_key': 'submit-before-delete' if action == 'submit' else action,
            }, format='json')
            self.assertEqual(response.status_code, 404, response.data)
        response = self.client.post(self.material_url(draft) + 'revisions/', {
            'task_ids': [self.task.pk], 'metadata': metadata('Cannot resurrect.'),
        }, format='json')
        self.assertEqual(response.status_code, 404)
        # Services lock and reload the row, so stale caller objects cannot resurrect it.
        with self.assertRaises(NotFound):
            new_revision(actor=self.teacher, material=draft.material, tasks=[self.task], metadata=metadata())
        with self.assertRaises(NotFound):
            parse_candidate(revision_id=draft.pk, token=draft.ingestion_token)
        self.assertEqual(draft.material.revisions.count(), 1)
        self.assert_unchanged()

    def test_ordinary_withdrawal_stays_manageable_and_can_later_be_deleted(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post(self.url + 'withdraw/', self.payload(idempotency_key='withdraw-one'), format='json')
        self.assertEqual(response.status_code, 200)
        rows = self.client.get(self.root + 'materials/').data['results']
        self.assertEqual(rows[0]['material_id'], str(self.revision.material.material_id))
        self.assertEqual(self.client.get(self.url + 'chunks/').status_code, 200)
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['acl_version'], 3)
        self.assertEqual(ReviewAction.objects.count(), 2)

    def test_database_authorization_failure_is_private_503(self):
        with patch('learning_knowledge.review.Material.objects.select_for_update', side_effect=OperationalError('Synthetic DB failure.')):
            response = self.delete()
        self.assertEqual(response.status_code, 503)
        self.assert_private(response)
        self.assert_unchanged()

    def test_delete_and_review_audit_write_are_atomic(self):
        token = self.revision.material.ingestion_token
        with patch('learning_knowledge.review.ReviewAction.objects.create', side_effect=RuntimeError('Synthetic audit failure.')):
            with self.assertRaises(RuntimeError):
                self.delete()
        self.assert_unchanged()
        self.assertEqual(self.revision.material.ingestion_token, token)
