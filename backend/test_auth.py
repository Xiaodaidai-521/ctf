from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase


class AuthenticationSmokeTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.admin = self.user_model.objects.create_user(
            username='admin',
            password='admin123456',
            role='admin',
        )

    def test_admin_credentials_authenticate(self):
        user = authenticate(username='admin', password='admin123456')
        self.assertIsNotNone(user)
        self.assertEqual(user.username, 'admin')
        self.assertEqual(user.role, 'admin')

    def test_admin_password_hash_verifies(self):
        admin = self.user_model.objects.get(username='admin')
        self.assertTrue(admin.check_password('admin123456'))

    def test_created_users_are_queryable(self):
        users = list(self.user_model.objects.values_list('username', 'role'))
        self.assertIn(('admin', 'admin'), users)
