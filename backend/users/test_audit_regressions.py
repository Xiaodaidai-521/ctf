from django.test import TestCase
from rest_framework.test import APIClient

from .models import CTFUser


class UserListRegressionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = CTFUser.objects.create_user(username='audit-admin', is_staff=True)
        for index, score in enumerate((100, 80, 60, 40)):
            CTFUser.objects.create_user(username=f'audit-ranked-{index}', score=score)

    def test_leaderboard_ranks_continue_across_pages(self):
        response = self.client.get('/api/users/leaderboard/', {'page': 2, 'page_size': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['rank'] for row in response.data['rankings']], [3, 4])

    def test_invalid_pagination_is_a_client_error(self):
        for path in ('/api/users/leaderboard/', '/api/users/admin/users/'):
            if 'admin/' in path:
                self.client.force_authenticate(self.admin)
            for params in ({'page': 'bad'}, {'page': '-1'}, {'page_size': '0'}, {'page_size': '-1'}):
                with self.subTest(path=path, params=params):
                    response = self.client.get(path, params)
                    self.assertEqual(response.status_code, 400)

    def test_page_size_is_bounded(self):
        response = self.client.get('/api/users/leaderboard/', {'page_size': 100000})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['page_size'], 100)
