"""Creation and draft-read contracts for the path management API."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from challenges.models import Category, Challenge
from .models import (
    LearningPath, ModuleLab, PathModule, UserLearningBehavior,
    UserModuleProgress, UserPathProgress,
)


class PathCreationAndDraftTests(TestCase):
    """Exercise real serializers, role permissions and persisted model fields."""

    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.teacher = users.objects.create_user(username='path-create-teacher', role='teacher')
        # Role-only administrators must not depend on Django's staff flag.
        cls.admin = users.objects.create_user(username='path-create-admin', role='admin')
        cls.student = users.objects.create_user(username='path-create-student', role='student')
        cls.staff_student = users.objects.create_user(
            username='path-create-staff-student', role='student', is_staff=True,
        )
        cls.inactive_teacher = users.objects.create_user(
            username='path-create-inactive', role='teacher', is_active=False,
        )
        cls.draft = LearningPath.objects.create(
            title='Draft path', slug='draft-path', description='Private draft description',
            difficulty='AP', is_published=False,
        )
        cls.published = LearningPath.objects.create(
            title='Published path', slug='published-path', description='Public description',
            difficulty='PR', is_published=True,
        )
        cls.other_draft = LearningPath.objects.create(
            title='Another draft', slug='other-draft', description='Another private path',
            difficulty='EX', is_published=False,
        )
        cls.draft_module = PathModule.objects.create(
            learning_path=cls.draft, title='Draft module', module_type='theory',
            content='# Private draft content',
        )
        cls.published_module = PathModule.objects.create(
            learning_path=cls.published, title='Published module', module_type='intro',
            content='# Public module content',
        )
        cls.other_module = PathModule.objects.create(
            learning_path=cls.other_draft, title='Other module', module_type='practice',
            content='# Other private content',
        )
        cls.draft_child = PathModule.objects.create(
            learning_path=cls.draft, parent_module=cls.draft_module,
            title='Draft child', module_type='theory', content='Private nested content',
        )
        cls.published_child = PathModule.objects.create(
            learning_path=cls.published, parent_module=cls.published_module,
            title='Published child', module_type='theory', content='Public nested content',
        )
        category = Category.objects.create(name='Path creation fixtures')
        for module, label in ((cls.draft_module, 'Draft'), (cls.published_module, 'Public')):
            lab = Challenge.objects.create(
                title=f'{label} lab', description=f'{label} lab description',
                category=category, difficulty='easy', score=10, flag='flag{synthetic}',
            )
            ModuleLab.objects.create(module=module, lab=lab)

    def setUp(self):
        self.client = APIClient()
        self.path_list = reverse('learning-path-list')
        self.module_list = reverse('path-module-list')

    def _authenticate(self, actor):
        self.client.force_authenticate(user=actor)

    def _path_payload(self, **overrides):
        payload = {
            'title': 'Security fundamentals', 'description': 'An authorized learning path.',
            'difficulty': 'PR', 'estimated_hours': 2.5, 'color': '#123abc',
            'order': 7, 'is_published': False,
        }
        payload.update(overrides)
        return payload

    def _module_payload(self, **overrides):
        payload = {
            'learning_path': self.draft.pk, 'title': 'Request validation',
            'description': 'Validate requests in an authorized environment.',
            'module_type': 'practice', 'content': '# Request validation\n\nUse a local fixture.',
            'order': 3, 'is_required': False, 'estimated_minutes': 45,
        }
        payload.update(overrides)
        return payload

    def _rows(self, response):
        self.assertEqual(response.status_code, 200, response.data)
        if isinstance(response.data, dict):
            self.assertIsNone(response.data['next'], 'Fixture must fit in one page.')
            return response.data['results']
        return response.data

    def _assert_path_created(self, actor):
        self._authenticate(actor)
        payload = self._path_payload()
        before = LearningPath.objects.count()
        response = self.client.post(self.path_list, payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsInstance(response.data['id'], int)
        self.assertEqual(LearningPath.objects.count(), before + 1)
        path = LearningPath.objects.get(pk=response.data['id'])
        for field, value in payload.items():
            with self.subTest(field=field):
                self.assertEqual(getattr(path, field), value)
                self.assertEqual(response.data[field], value)
        self.assertEqual(response.data['slug'], path.slug)
        self.assertNotIn('is_active', response.data)
        detail = self.client.get(reverse('learning-path-detail', args=[path.pk]))
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data['id'], path.pk)
        self.assertEqual(detail.data['slug'], path.slug)
        listed = {row['id']: row for row in self._rows(self.client.get(self.path_list))}
        self.assertEqual(listed[path.pk]['slug'], path.slug)

    def _assert_module_created(self, actor):
        self._authenticate(actor)
        payload = self._module_payload()
        before = PathModule.objects.count()
        response = self.client.post(self.module_list, payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsInstance(response.data['id'], int)
        self.assertEqual(PathModule.objects.count(), before + 1)
        module = PathModule.objects.get(pk=response.data['id'])
        self.assertEqual(module.learning_path_id, self.draft.pk)
        self.assertEqual(response.data['learning_path'], self.draft.pk)
        for field, value in payload.items():
            if field != 'learning_path':
                with self.subTest(field=field):
                    self.assertEqual(getattr(module, field), value)
                    self.assertEqual(response.data[field], value)
        self.assertIsNone(module.parent_module_id)
        self.assertFalse(module.requires_modules.exists())
        self.assertNotIn('theory_content', response.data)
        self.assertNotIn('theory_url', response.data)
        detail = self.client.get(reverse('path-module-detail', args=[module.pk]))
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data['id'], module.pk)
        self.assertEqual(detail.data['content'], payload['content'])

    def _assert_invalid_creation(self, family, payload, field):
        model, url = ((LearningPath, self.path_list) if family == 'path'
                      else (PathModule, self.module_list))
        for actor in (self.teacher, self.admin):
            with self.subTest(role=actor.role):
                self._authenticate(actor)
                before = model.objects.count()
                response = self.client.post(url, payload, format='json')
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field, response.data)
                self.assertEqual(model.objects.count(), before)

    def test_teacher_creates_path_with_real_fields_and_readable_id(self):
        self._assert_path_created(self.teacher)

    def test_admin_creates_path_without_staff_flag(self):
        self.assertFalse(self.admin.is_staff)
        self._assert_path_created(self.admin)

    def test_path_defaults_to_unpublished_when_flag_omitted(self):
        for actor in (self.teacher, self.admin):
            with self.subTest(role=actor.role):
                self._authenticate(actor)
                payload = self._path_payload()
                del payload['is_published']
                response = self.client.post(self.path_list, payload, format='json')
                self.assertEqual(response.status_code, 201, response.data)
                self.assertFalse(response.data['is_published'])
                self.assertFalse(LearningPath.objects.get(pk=response.data['id']).is_published)

    def test_explicit_slug_is_preserved_for_teacher_and_admin(self):
        for actor in (self.teacher, self.admin):
            with self.subTest(role=actor.role):
                self._authenticate(actor)
                slug = f'explicit-{actor.role}'
                response = self.client.post(
                    self.path_list, self._path_payload(slug=slug, is_published=True), format='json',
                )
                self.assertEqual(response.status_code, 201, response.data)
                path = LearningPath.objects.get(pk=response.data['id'])
                self.assertEqual(path.slug, slug)
                self.assertEqual(response.data['slug'], slug)
                self.assertTrue(path.is_published)

    def test_ascii_title_gets_valid_automatic_slug(self):
        self._authenticate(self.teacher)
        response = self.client.post(self.path_list, self._path_payload(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertRegex(response.data['slug'], r'^security-fundamentals-[0-9a-f]{32}$')

    def test_non_ascii_title_gets_nonempty_automatic_slug(self):
        self._authenticate(self.admin)
        response = self.client.post(
            self.path_list, self._path_payload(title='安全基础学习航线'), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertRegex(response.data['slug'], r'^learning-path-[0-9a-f]{32}$')
        self.assertEqual(LearningPath.objects.get(pk=response.data['id']).slug, response.data['slug'])

    def test_repeated_titles_get_distinct_automatic_slugs(self):
        slugs = []
        for actor in (self.teacher, self.admin):
            self._authenticate(actor)
            response = self.client.post(self.path_list, self._path_payload(), format='json')
            self.assertEqual(response.status_code, 201, response.data)
            slugs.append(response.data['slug'])
        self.assertEqual(len(set(slugs)), 2)
        self.assertEqual(LearningPath.objects.filter(slug__in=slugs).count(), 2)

    def test_explicit_slug_accepts_model_length_boundary(self):
        self._authenticate(self.teacher)
        slug = 's' * LearningPath._meta.get_field('slug').max_length
        response = self.client.post(self.path_list, self._path_payload(slug=slug), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(LearningPath.objects.get(pk=response.data['id']).slug, slug)

    def test_maximum_length_title_generates_slug_within_model_limit(self):
        self._authenticate(self.teacher)
        response = self.client.post(
            self.path_list,
            self._path_payload(title='a' * LearningPath._meta.get_field('title').max_length),
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertLessEqual(len(response.data['slug']), LearningPath._meta.get_field('slug').max_length)
        self.assertRegex(response.data['slug'], r'^[a-zA-Z0-9_-]+$')

    def test_path_title_over_model_length_is_400(self):
        self._assert_invalid_creation('path', self._path_payload(title='t' * 201), 'title')

    def test_explicit_slug_over_model_length_is_400(self):
        self._assert_invalid_creation('path', self._path_payload(slug='s' * 201), 'slug')

    def test_duplicate_explicit_slug_is_400_even_for_hidden_draft(self):
        self._assert_invalid_creation('path', self._path_payload(slug=self.draft.slug), 'slug')

    def test_invalid_explicit_slug_is_400(self):
        self._assert_invalid_creation('path', self._path_payload(slug='not a/slug'), 'slug')

    def test_blank_explicit_slug_is_400_instead_of_saved_empty(self):
        self._assert_invalid_creation('path', self._path_payload(slug=''), 'slug')

    def test_path_required_fields_reject_missing_and_blank(self):
        for field in ('title', 'description', 'difficulty'):
            for missing in (True, False):
                with self.subTest(field=field, missing=missing):
                    payload = self._path_payload()
                    if missing:
                        del payload[field]
                    else:
                        payload[field] = ''
                    self._assert_invalid_creation('path', payload, field)

    def test_path_difficulty_uses_model_choices(self):
        self._assert_invalid_creation('path', self._path_payload(difficulty='easy'), 'difficulty')

    def test_teacher_creates_module_with_path_content_and_id(self):
        self._assert_module_created(self.teacher)

    def test_admin_creates_module_with_path_content_and_id(self):
        self._assert_module_created(self.admin)

    def test_module_required_fields_reject_missing_and_blank(self):
        for field in ('learning_path', 'title', 'module_type', 'content'):
            for missing in (True, False):
                with self.subTest(field=field, missing=missing):
                    payload = self._module_payload()
                    if missing:
                        del payload[field]
                    else:
                        payload[field] = ''
                    self._assert_invalid_creation('module', payload, field)

    def test_module_nonexistent_path_is_400(self):
        self._assert_invalid_creation('module', self._module_payload(learning_path=999999), 'learning_path')

    def test_module_type_uses_model_choices(self):
        self._assert_invalid_creation('module', self._module_payload(module_type='unknown'), 'module_type')

    def test_module_parent_from_same_path_is_persisted(self):
        for actor in (self.teacher, self.admin):
            with self.subTest(role=actor.role):
                self._authenticate(actor)
                response = self.client.post(
                    self.module_list, self._module_payload(parent_module=self.draft_module.pk), format='json',
                )
                self.assertEqual(response.status_code, 201, response.data)
                module = PathModule.objects.get(pk=response.data['id'])
                self.assertEqual(module.parent_module_id, self.draft_module.pk)
                self.assertEqual(response.data['parent_module'], self.draft_module.pk)
                detail = self.client.get(reverse('learning-path-detail', args=[self.draft.pk]))
                self.assertEqual(detail.status_code, 200, detail.data)
                parent = next(row for row in detail.data['modules'] if row['id'] == self.draft_module.pk)
                self.assertIn(module.pk, [row['id'] for row in parent['sub_modules']])

    def test_module_prerequisites_from_same_path_are_persisted_and_readable(self):
        for actor in (self.teacher, self.admin):
            with self.subTest(role=actor.role):
                self._authenticate(actor)
                requires = [self.draft_module.pk, self.draft_child.pk]
                response = self.client.post(
                    self.module_list, self._module_payload(requires=requires), format='json',
                )
                self.assertEqual(response.status_code, 201, response.data)
                module = PathModule.objects.get(pk=response.data['id'])
                self.assertSetEqual(set(module.requires_modules.values_list('pk', flat=True)), set(requires))
                detail = self.client.get(reverse('path-module-detail', args=[module.pk]))
                self.assertEqual(detail.status_code, 200, detail.data)
                self.assertSetEqual(set(detail.data['requires']), set(requires))

    def test_module_cross_path_parent_is_400(self):
        self._assert_invalid_creation(
            'module', self._module_payload(parent_module=self.other_module.pk), 'parent_module',
        )

    def test_module_cross_path_prerequisite_is_400_including_mixed_list(self):
        for requires in ([self.other_module.pk], [self.draft_module.pk, self.other_module.pk]):
            with self.subTest(requires=requires):
                self._assert_invalid_creation('module', self._module_payload(requires=requires), 'requires')

    def test_module_nonexistent_parent_is_400(self):
        self._assert_invalid_creation('module', self._module_payload(parent_module=999999), 'parent_module')

    def test_module_nonexistent_prerequisite_is_400(self):
        self._assert_invalid_creation('module', self._module_payload(requires=[999999]), 'requires')

    def test_module_title_over_model_length_is_400(self):
        self._assert_invalid_creation('module', self._module_payload(title='m' * 201), 'title')

    def _assert_manager_list(self, actor, family):
        self._authenticate(actor)
        url, model = ((self.path_list, LearningPath) if family == 'path'
                      else (self.module_list, PathModule))
        rows = self._rows(self.client.get(url))
        self.assertSetEqual({row['id'] for row in rows}, set(model.objects.values_list('pk', flat=True)))
        if family == 'path':
            draft = next(row for row in rows if row['id'] == self.draft.pk)
            self.assertFalse(draft['is_published'])
            self.assertEqual(draft['slug'], self.draft.slug)
        else:
            for query in ('path', 'learning_path'):
                with self.subTest(query=query):
                    rows = self._rows(self.client.get(url, {query: self.draft.pk}))
                    self.assertSetEqual({row['id'] for row in rows}, {self.draft_module.pk, self.draft_child.pk})

    def _assert_manager_detail(self, actor, family):
        self._authenticate(actor)
        instance, route = ((self.draft, 'learning-path-detail') if family == 'path'
                           else (self.draft_module, 'path-module-detail'))
        response = self.client.get(reverse(route, args=[instance.pk]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['id'], instance.pk)
        if family == 'path':
            self.assertFalse(response.data['is_published'])
            self.assertEqual(response.data['slug'], self.draft.slug)
            self.assertIn(self.draft_module.pk, [row['id'] for row in response.data['modules']])
        else:
            self.assertEqual(response.data['content'], self.draft_module.content)

    def _assert_manager_update(self, actor, family):
        self._authenticate(actor)
        instance, route = ((self.draft, 'learning-path-detail') if family == 'path'
                           else (self.draft_module, 'path-module-detail'))
        for method in ('put', 'patch'):
            with self.subTest(method=method):
                title = f'{actor.role} {method} updated draft'
                if family == 'path':
                    payload = self._path_payload(title=title, slug='must-not-change-on-update')
                else:
                    payload = self._module_payload(title=title, content=f'# {title}')
                if method == 'patch':
                    payload = {field: payload[field] for field in
                               (('title', 'slug') if family == 'path' else ('title', 'content'))}
                response = getattr(self.client, method)(reverse(route, args=[instance.pk]), payload, format='json')
                self.assertEqual(response.status_code, 200, response.data)
                instance.refresh_from_db()
                self.assertEqual(instance.title, title)
                self.assertFalse(self.draft.is_published)
                if family == 'path':
                    self.assertEqual(instance.slug, 'draft-path')
                    self.assertEqual(response.data['slug'], 'draft-path')
                else:
                    self.assertEqual(instance.content, payload['content'])
                    self.assertEqual(instance.learning_path_id, self.draft.pk)
                self._assert_manager_detail(actor, family)

    def test_teacher_lists_draft_paths(self):
        self._assert_manager_list(self.teacher, 'path')

    def test_admin_lists_draft_paths(self):
        self._assert_manager_list(self.admin, 'path')

    def test_teacher_reads_draft_path_detail(self):
        self._assert_manager_detail(self.teacher, 'path')

    def test_admin_reads_draft_path_detail(self):
        self._assert_manager_detail(self.admin, 'path')

    def test_teacher_updates_draft_path_with_slug_readonly(self):
        self._assert_manager_update(self.teacher, 'path')

    def test_admin_updates_draft_path_with_slug_readonly(self):
        self._assert_manager_update(self.admin, 'path')

    def test_teacher_lists_draft_modules(self):
        self._assert_manager_list(self.teacher, 'module')

    def test_admin_lists_draft_modules(self):
        self._assert_manager_list(self.admin, 'module')

    def test_teacher_reads_draft_module_detail(self):
        self._assert_manager_detail(self.teacher, 'module')

    def test_admin_reads_draft_module_detail(self):
        self._assert_manager_detail(self.admin, 'module')

    def test_teacher_updates_draft_module(self):
        self._assert_manager_update(self.teacher, 'module')

    def test_admin_updates_draft_module(self):
        self._assert_manager_update(self.admin, 'module')

    def _assert_published_only(self, actor, family):
        self._authenticate(actor)
        if family == 'path':
            url, route = self.path_list, 'learning-path-detail'
            visible, hidden = [self.published], [self.draft, self.other_draft]
        else:
            url, route = self.module_list, 'path-module-detail'
            visible = [self.published_module, self.published_child]
            hidden = [self.draft_module, self.draft_child, self.other_module]
        rows = self._rows(self.client.get(url))
        self.assertSetEqual({row['id'] for row in rows}, {obj.pk for obj in visible})
        for instance in visible:
            with self.subTest(visible_id=instance.pk):
                response = self.client.get(reverse(route, args=[instance.pk]))
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['id'], instance.pk)
        for instance in hidden:
            with self.subTest(hidden_id=instance.pk):
                response = self.client.get(reverse(route, args=[instance.pk]))
                self.assertEqual(response.status_code, 404, response.data)
        if family == 'path':
            response = self.client.get(url, {'search': 'Private draft'})
            self.assertEqual(self._rows(response), [])
        else:
            for query in ('path', 'learning_path'):
                with self.subTest(query=query):
                    self.assertEqual(self._rows(self.client.get(url, {query: self.draft.pk})), [])

    def _assert_publication_toggle(self, actor):
        for published in (True, False):
            with self.subTest(is_published=published):
                self._authenticate(actor)
                response = self.client.patch(
                    reverse('learning-path-detail', args=[self.draft.pk]),
                    {'is_published': published}, format='json',
                )
                self.assertEqual(response.status_code, 200, response.data)
                self.draft.refresh_from_db()
                self.assertEqual(self.draft.is_published, published)
                for reader in (self.student, self.staff_student, None):
                    with self.subTest(reader=reader.username if reader else 'anonymous'):
                        self._authenticate(reader)
                        for route, instance in (
                            ('learning-path-detail', self.draft),
                            ('path-module-detail', self.draft_module),
                            ('path-module-detail', self.draft_child),
                        ):
                            response = self.client.get(reverse(route, args=[instance.pk]))
                            self.assertEqual(response.status_code, 200 if published else 404, response.data)
                        paths = self._rows(self.client.get(self.path_list))
                        self.assertEqual(self.draft.pk in {row['id'] for row in paths}, published)
                        modules = self._rows(self.client.get(self.module_list, {'path': self.draft.pk}))
                        self.assertSetEqual(
                            {row['id'] for row in modules},
                            {self.draft_module.pk, self.draft_child.pk} if published else set(),
                        )
                self._assert_manager_detail(actor, 'module')
        self._assert_manager_detail(actor, 'path')

    def test_teacher_can_publish_and_return_path_to_draft(self):
        self._assert_publication_toggle(self.teacher)

    def test_admin_can_publish_and_return_path_to_draft(self):
        self._assert_publication_toggle(self.admin)

    def test_student_path_list_and_detail_only_expose_published(self):
        self._assert_published_only(self.student, 'path')

    def test_anonymous_path_list_and_detail_only_expose_published(self):
        self._assert_published_only(None, 'path')

    def test_staff_student_path_list_and_detail_only_expose_published(self):
        self._assert_published_only(self.staff_student, 'path')

    def test_student_module_list_and_detail_only_expose_published(self):
        self._assert_published_only(self.student, 'module')

    def test_anonymous_module_list_and_detail_only_expose_published(self):
        self._assert_published_only(None, 'module')

    def test_staff_student_module_list_and_detail_only_expose_published(self):
        self._assert_published_only(self.staff_student, 'module')

    def test_nonmanagers_cannot_create_paths_or_modules(self):
        for actor in (self.student, self.staff_student, None):
            self._authenticate(actor)
            for url, payload, model in (
                (self.path_list, self._path_payload(), LearningPath),
                (self.module_list, self._module_payload(), PathModule),
            ):
                with self.subTest(actor=actor.username if actor else 'anonymous', model=model.__name__):
                    before = model.objects.count()
                    response = self.client.post(url, payload, format='json')
                    self.assertIn(response.status_code, (401, 403), response.data)
                    self.assertEqual(model.objects.count(), before)

    def test_nonmanagers_cannot_update_published_or_draft_content(self):
        for actor in (self.student, self.staff_student, None):
            self._authenticate(actor)
            for route, instance in (
                ('learning-path-detail', self.draft), ('learning-path-detail', self.published),
                ('path-module-detail', self.draft_module), ('path-module-detail', self.published_module),
            ):
                with self.subTest(actor=actor.username if actor else 'anonymous', route=route, pk=instance.pk):
                    original = instance.title
                    response = self.client.patch(
                        reverse(route, args=[instance.pk]), {'title': 'Unauthorized change'}, format='json',
                    )
                    self.assertIn(response.status_code, (401, 403), response.data)
                    instance.refresh_from_db()
                    self.assertEqual(instance.title, original)

    def test_inactive_teacher_reads_only_published_paths_and_modules(self):
        self._assert_published_only(self.inactive_teacher, 'path')
        self._assert_published_only(self.inactive_teacher, 'module')

    def test_inactive_teacher_cannot_create_path_or_module(self):
        self._authenticate(self.inactive_teacher)
        for url, payload, model in (
            (self.path_list, self._path_payload(), LearningPath),
            (self.module_list, self._module_payload(), PathModule),
        ):
            with self.subTest(model=model.__name__):
                before = model.objects.count()
                response = self.client.post(url, payload, format='json')
                self.assertEqual(response.status_code, 403, response.data)
                self.assertEqual(model.objects.count(), before)

    def _assert_draft_learning_actions_hidden(self, actor):
        self._authenticate(actor)
        path_progress = module_progress = None
        if actor:
            # Existing progress prevents an unrelated "not started" 404 from
            # masking missing draft filtering in progress/complete actions.
            path_progress = UserPathProgress.objects.create(
                user=actor, learning_path=self.draft, current_module=self.draft_module,
                total_modules=2,
            )
            module_progress = UserModuleProgress.objects.create(
                user=actor, module=self.draft_module, status='IN_PROGRESS',
            )
        for route, pk, method in (
            ('learning-path-start', self.draft.pk, 'post'),
            ('learning-path-progress', self.draft.pk, 'get'),
            ('path-module-start', self.draft_module.pk, 'post'),
            ('path-module-complete', self.draft_module.pk, 'post'),
            ('path-module-labs', self.draft_module.pk, 'get'),
        ):
            with self.subTest(route=route):
                response = getattr(self.client, method)(reverse(route, args=[pk]))
                if actor or method == 'get':
                    self.assertEqual(response.status_code, 404, response.data)
                else:
                    self.assertIn(response.status_code, (401, 403), response.data)
        self.assertFalse(UserLearningBehavior.objects.exists())
        if actor:
            path_progress.refresh_from_db()
            module_progress.refresh_from_db()
            self.assertEqual(module_progress.status, 'IN_PROGRESS')
            self.assertIsNone(module_progress.started_at)
            self.assertIsNone(module_progress.completed_at)
            self.assertEqual(path_progress.completed_modules, 0)
            self.assertEqual(path_progress.progress_percentage, 0)

    def test_student_cannot_use_learning_actions_on_drafts(self):
        self._assert_draft_learning_actions_hidden(self.student)

    def test_staff_student_cannot_use_learning_actions_on_drafts(self):
        self._assert_draft_learning_actions_hidden(self.staff_student)

    def test_anonymous_cannot_use_learning_actions_on_drafts(self):
        self._assert_draft_learning_actions_hidden(None)

    def test_manager_draft_read_permission_does_not_extend_to_learning_actions(self):
        for actor in (self.teacher, self.admin):
            with self.subTest(role=actor.role):
                self._assert_draft_learning_actions_hidden(actor)

    def test_published_module_labs_remain_publicly_readable(self):
        for actor in (self.student, self.staff_student, None):
            with self.subTest(actor=actor.username if actor else 'anonymous'):
                self._authenticate(actor)
                response = self.client.get(reverse('path-module-labs', args=[self.published_module.pk]))
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(len(response.data), 1)
                self.assertEqual(response.data[0]['lab_title'], 'Public lab')
                self.assertNotIn('flag', response.data[0])

    def test_student_can_still_start_published_path_and_module_and_read_progress(self):
        self._authenticate(self.student)
        response = self.client.post(reverse('learning-path-start', args=[self.published.pk]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['learning_path'], self.published.pk)
        response = self.client.post(reverse('path-module-start', args=[self.published_module.pk]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['module'], self.published_module.pk)
        self.assertEqual(response.data['status'], 'IN_PROGRESS')
        response = self.client.get(reverse('learning-path-progress', args=[self.published.pk]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['learning_path'], self.published.pk)
        self.assertEqual(response.data['current_module'], self.published_module.pk)
