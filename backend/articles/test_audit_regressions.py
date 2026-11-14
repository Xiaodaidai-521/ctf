from django.test import TestCase
from rest_framework.test import APIClient

from users.models import CTFUser
from .models import Article, ArticleCollect, Comment


class CommunityBoundaryRegressionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.author = CTFUser.objects.create_user(username='audit-author')
        self.peer = CTFUser.objects.create_user(username='audit-peer')
        self.admin = CTFUser.objects.create_user(username='audit-editor', is_staff=True)
        self.published = Article.objects.create(author=self.author, title='Published', content='public', status='approved')
        self.pending = Article.objects.create(author=self.author, title='Draft', content='private draft', status='pending')
        self.rejected = Article.objects.create(author=self.author, title='Rejected', content='private rejection', status='rejected')
        self.comment = Comment.objects.create(author=self.author, article=self.published, content='original comment')
        self.private_comment = Comment.objects.create(author=self.author, article=self.pending, content='private comment')

    @staticmethod
    def rows(response):
        return response.data.get('results', response.data) if isinstance(response.data, dict) else response.data

    def test_status_filter_cannot_reveal_unpublished_articles(self):
        for actor in (None, self.peer):
            self.client.force_authenticate(actor)
            for article in (self.pending, self.rejected):
                with self.subTest(actor=actor, status=article.status):
                    listing = self.client.get('/api/articles/articles/', {'status': article.status})
                    self.assertEqual(listing.status_code, 200)
                    self.assertEqual(self.rows(listing), [])
                    detail = self.client.get(f'/api/articles/articles/{article.pk}/', {'status': article.status})
                    self.assertEqual(detail.status_code, 404)

    def test_author_can_read_and_edit_own_pending_article(self):
        self.client.force_authenticate(self.author)
        response = self.client.get('/api/articles/articles/my/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['id'] for row in self.rows(response)}, {self.published.pk, self.pending.pk, self.rejected.pk})
        detail = self.client.get(f'/api/articles/articles/{self.pending.pk}/')
        self.assertEqual(detail.status_code, 200)
        updated = self.client.patch(f'/api/articles/articles/{self.pending.pk}/', {'title': 'Edited draft'}, format='json')
        self.assertEqual(updated.status_code, 200)

    def test_anonymous_personal_lists_require_authentication(self):
        for action in ('my', 'my_favorites'):
            with self.subTest(action=action):
                self.assertEqual(self.client.get(f'/api/articles/articles/{action}/').status_code, 403)

    def test_withdrawn_favorite_and_comments_are_hidden_from_other_users(self):
        ArticleCollect.objects.create(user=self.peer, article=self.pending)
        self.client.force_authenticate(self.peer)
        favorites = self.client.get('/api/articles/articles/my_favorites/')
        self.assertEqual(favorites.status_code, 200)
        self.assertEqual(self.rows(favorites), [])
        comments = self.client.get('/api/articles/comments/', {'article': self.pending.pk})
        self.assertEqual(comments.status_code, 200)
        self.assertEqual(self.rows(comments), [])
        detail = self.client.get(f'/api/articles/comments/{self.private_comment.pk}/')
        self.assertEqual(detail.status_code, 404)

    def test_other_user_cannot_update_comment(self):
        self.client.force_authenticate(self.peer)
        response = self.client.patch(f'/api/articles/comments/{self.comment.pk}/', {'content': 'overwritten'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.content, 'original comment')

    def test_comment_cannot_be_reparented_or_moved_to_another_article(self):
        self.client.force_authenticate(self.author)
        response = self.client.patch(f'/api/articles/comments/{self.comment.pk}/', {'article': self.pending.pk}, format='json')
        self.assertEqual(response.status_code, 200)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.article_id, self.published.pk)

    def test_comment_cannot_be_added_to_another_authors_unpublished_article(self):
        self.client.force_authenticate(self.peer)
        response = self.client.post('/api/articles/comments/', {'article': self.pending.pk, 'content': 'unexpected comment'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Comment.objects.filter(author=self.peer, article=self.pending).exists())

    def test_invalid_article_query_is_a_client_error(self):
        for params in ({'ordering': 'nonexistent_field'}, {'author': 'invalid'}, {'category': 'invalid'}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get('/api/articles/articles/', params).status_code, 400)
        for action in ('hot', 'recommend'):
            for limit in ('invalid', '-1', '0'):
                with self.subTest(action=action, limit=limit):
                    self.assertEqual(self.client.get(f'/api/articles/articles/{action}/', {'limit': limit}).status_code, 400)

    def test_admin_can_review_pending_articles(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/articles/articles/{self.pending.pk}/review/', {'status': 'approved'}, format='json')
        self.assertEqual(response.status_code, 200)
