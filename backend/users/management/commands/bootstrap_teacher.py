import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


def is_truthy(value):
    return value.lower() in ('true', '1', 'yes')


class Command(BaseCommand):
    help = 'Create or align the configured teacher account.'

    def handle(self, *args, **options):
        username = os.environ.get('TEACHER_USERNAME', 'Teacher_李')
        password = os.environ.get('TEACHER_PASSWORD', '123456')

        User = get_user_model()
        teacher, created = User.objects.get_or_create(username=username)
        teacher.email = os.environ.get('TEACHER_EMAIL', 'teacher_li@example.com')
        teacher.role = 'teacher'
        teacher.is_staff = False
        teacher.is_superuser = False

        if created or is_truthy(os.environ.get('TEACHER_RESET_PASSWORD', 'false')):
            teacher.set_password(password)

        teacher.save()
        message = 'Teacher demo account created' if created else 'Teacher demo account verified'
        self.stdout.write(message)

