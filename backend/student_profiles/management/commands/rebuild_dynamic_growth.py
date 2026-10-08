from django.core.management.base import BaseCommand, CommandError

from users.models import CTFUser
from student_profiles.growth_service import refresh_dynamic_growth


class Command(BaseCommand):
    help = 'Rebuild a user dynamic growth profile from persisted learning evidence.'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, required=True)

    def handle(self, *args, **options):
        user = CTFUser.objects.filter(id=options['user_id']).first()
        if not user:
            raise CommandError(
                f'User {options["user_id"]} does not exist; no data was created.'
            )
        summary = refresh_dynamic_growth(user)
        self.stdout.write(self.style.SUCCESS(
            f'Rebuilt user {user.id}: status={summary["analysis_status"]}, '
            f'completed={summary["completed_question_count"]}, '
            f'learning_seconds={summary["total_learning_seconds"]}'
        ))
