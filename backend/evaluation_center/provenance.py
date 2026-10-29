from .models import NonFormalAccount


def excluded_student_ids():
    return NonFormalAccount.objects.values_list('student_id', flat=True)


def formal_students():
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(role='student', is_active=True).exclude(
        pk__in=excluded_student_ids(),
    )
