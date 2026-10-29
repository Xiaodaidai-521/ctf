from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from learning_knowledge.models import CourseGrant, Material, MaterialRevision, MaterialChunk, TaskMaterial
from learning_knowledge.policy import Scope, digest
from teaching_agent.tests.test_context_permissions import make_task_attempt
from users.models import CTFUser


def setup_case(case):
    case.student = CTFUser.objects.create_user(username='m3-student', role='student')
    case.other = CTFUser.objects.create_user(username='m3-other', role='student')
    case.teacher = CTFUser.objects.create_user(username='m3-teacher', role='teacher')
    case.admin = CTFUser.objects.create_user(username='m3-admin', role='admin', is_staff=True)
    case.task, case.attempt = make_task_attempt(case.student, suffix='m3')
    for user in (case.student, case.teacher):
        CourseGrant.objects.create(user=user, catalog=case.task.catalog, can_review=user == case.teacher)
    case.scope = Scope(case.student, case.attempt.attempt_id)


def material(case, material_class='lesson', *, text='检查授权范围并保留证据。', status='published', source_type='teacher_authored', source_id=None, level=None):
    source = Material.objects.create(
        catalog=case.task.catalog, owner=case.teacher, material_class=material_class,
        source_type=source_type, source_object_id=source_id,
        published_scope='learner', hint_level=level,
    )
    revision = MaterialRevision.objects.create(
        material=source, revision=1, title=f'{material_class} title', publisher='测试原创',
        source_version='1', source_date=date(2026, 10, 29), verified_at=date(2026, 10, 29),
        source_hash=digest(text), source_snapshot=text,
        license_id='CC-BY-4.0', attribution_text='Synthetic test fixture', reuse_scope='教学',
        applicability='仅合成任务', review_status=status, parse_status='completed',
    )
    MaterialChunk.objects.create(revision=revision, index=0, start=0, end=len(text), chunk_hash=digest(text), locator={'paragraph': 1})
    TaskMaterial.objects.create(task=case.task, revision=revision, knowledge_point_ids=['KP-NS-01'])
    return revision


def scoped_source(user, source_type, source):
    """Synthetic trusted publication for old positive retrieval regression cases."""
    task, attempt = make_task_attempt(user, suffix=f'legacy-{uuid4().hex[:8]}')
    CourseGrant.objects.create(user=user, catalog=task.catalog)
    field = {'article': 'content', 'resource': 'description', 'knowledge_concept': 'description'}[source_type]
    revision = material(SimpleNamespace(task=task, teacher=user), text=getattr(source, field),
                        source_type=source_type, source_id=source.pk)
    revision.title = getattr(source, 'title', getattr(source, 'name', 'source'))
    revision.save(update_fields=['title'])
    return Scope(user, attempt.attempt_id)
