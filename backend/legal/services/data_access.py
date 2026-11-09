"""Owner-scoped legal queries; role alone never grants access to another subject."""
from django.db.models import Q

from data_security.adapters.persistence.fields import field_storage_enabled
from users.permissions import authorized_users

from ..models import LegalAnalysisTask


def authorized_legal_objects(queryset, actor, course_id=None):
    if not field_storage_enabled():
        return queryset
    users = list(authorized_users(actor, course_id).values_list('pk', flat=True))
    tasks = LegalAnalysisTask.objects.filter(
        Q(fact_snapshots__scope__subject_user_id__in=users) |
        Q(fact_snapshots__isnull=True, created_by__in=users)).values('pk')
    name = queryset.model._meta.model_name
    if name == 'legalanalysistask':
        return queryset.filter(pk__in=tasks)
    if name in ('legalriskfinding', 'complianceagentrun'):
        return queryset.filter(task_id__in=tasks)
    if name == 'legalevidence':
        return queryset.filter(Q(task_id__in=tasks) |
            Q(task__isnull=True, risk_finding__task_id__in=tasks))
    if name == 'legalreport':
        return queryset.filter(Q(task_id__in=tasks) |
            Q(task__isnull=True, generated_by__in=users))
    if name == 'legalfactsnapshot':
        return queryset.filter(scope__subject_user_id__in=users)
    return queryset.none()
