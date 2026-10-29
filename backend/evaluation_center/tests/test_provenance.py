from django.test import TestCase
from django.contrib.auth import get_user_model

from evaluation_center.models import NonFormalAccount
from evaluation_center.provenance import formal_students


class ProvenanceTests(TestCase):
    def test_explicit_demo_and_offline_accounts_excluded(self):
        user_model = get_user_model()
        real = user_model.objects.create_user(username='123', role='student')
        demo = user_model.objects.create_user(username='demo', role='student')
        offline = user_model.objects.create_user(username='offline', role='student')
        user_model.objects.create_user(username='teacher', role='teacher')
        NonFormalAccount.objects.create(student=demo, source='demo')
        NonFormalAccount.objects.create(student=offline, source='offline')
        self.assertEqual(list(formal_students()), [real])

    def test_empty_does_not_seed_demo(self):
        self.assertFalse(formal_students().exists())
        self.assertFalse(NonFormalAccount.objects.exists())
