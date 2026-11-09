from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from data_security.adapters.django.authentication import bootstrap_teacher_inputs


class Command(BaseCommand):
    help = 'Create or align a teacher account using explicitly supplied bootstrap credentials.'

    def handle(self, *args, **options):
        inputs = bootstrap_teacher_inputs()
        username = inputs['username']
        if not username:
            raise CommandError('TEACHER_USERNAME_REQUIRED')

        User = get_user_model()
        teacher = User.objects.filter(username=username).first()
        created = teacher is None
        if created:
            teacher = User(username=username)
        teacher.email = inputs['email']
        teacher.role = 'teacher'
        teacher.is_staff = False
        teacher.is_superuser = False

        if created or inputs['reset_password']:
            password = inputs.get('password')
            if not password:
                raise CommandError('TEACHER_PASSWORD_REQUIRED')
            try:
                validate_password(password, user=teacher)
            except ValidationError:
                raise CommandError('TEACHER_PASSWORD_REJECTED') from None
            teacher.set_password(password)

        teacher.save()
        message = 'Teacher account created' if created else 'Teacher account verified'
        self.stdout.write(message)
