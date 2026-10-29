"""Teacher coordination, not grading. Source conclusions remain in module six."""

from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from skill_review.models import (
    DownstreamNotice, ManualReviewTask, RetestAssignment, ScoreDispute,
    TeacherSamplingItem, VerificationResult,
)
from teaching_agent.models import TeacherTicket

from .models import ProjectionReceipt, TeacherTodo, TodoAction
from .permissions import is_teacher
from .projections import query_learning, retest_payload
from .provenance import excluded_student_ids


class OperationsError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def require_teacher(actor):
    if not is_teacher(actor):
        raise OperationsError('需要教师或管理员权限。', 403)


def _admin(actor):
    return actor.is_superuser or actor.role == 'admin'


def _scope(attempt):
    if attempt.student.role != 'student' or attempt.student_id in excluded_student_ids():
        raise OperationsError('只允许处理正式学生的教学待办。', 403)


def _day(value):
    start = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


@transaction.atomic
def create_todo(*, actor, attempt, kind='help', proposal=None, summary=''):
    require_teacher(actor)
    _scope(attempt)
    if kind not in dict(TeacherTodo._meta.get_field('kind').choices):
        raise OperationsError('待办类型不合法。')
    if proposal and (proposal.student_id != attempt.student_id or
                     (proposal.teacher_id != actor.pk and not _admin(actor))):
        raise OperationsError('提案归属不匹配；不得修改其他作者的提案。', 403)
    return _create(attempt, kind, f'manual:{uuid4()}', actor=actor, proposal=proposal, summary=summary)


def _create(attempt, kind, source_key, *, actor, proposal=None, summary='', snapshot=None, result=None):
    first = attempt.submissions.filter(first_effective=True).order_by('created_at').first()
    if result is None and first:
        result = first.results.filter(is_current=True).first()
    start, end = _day(first.created_at if first else attempt.claimed_at)
    todo, created = TeacherTodo.objects.get_or_create(source_key=source_key, defaults={
        'student': attempt.student, 'attempt': attempt, 'kind': kind, 'proposal': proposal,
        'summary': summary[:1000], 'original_result': result,
        'source_snapshot': snapshot or {}, 'window_start': start, 'window_end': end,
    })
    if created:
        TodoAction.objects.create(todo=todo, revision=1, action='created', actor=actor,
                                  old_owner_id=None, new_owner_id=None, summary=summary[:1000])
    return todo


@transaction.atomic
def sync_todos(*, actor):
    require_teacher(actor)
    excluded = excluded_student_ids()
    records = []
    for item in TeacherTicket.objects.exclude(student_id__in=excluded).filter(status__in=['open', 'claimed', 'helped']).select_related('attempt__student'):
        records.append(_create(item.attempt, 'help', f'm2:{item.ticket_id}', actor=actor,
                               snapshot={'ticket_id': str(item.ticket_id), 'source_status': item.status}))
    for item in ManualReviewTask.objects.exclude(student_id__in=excluded).filter(status__in=['pending', 'claimed']).select_related('attempt__student', 'result'):
        records.append(_create(item.attempt, 'manual_review', f'm6-manual:{item.review_id}', actor=actor, result=item.result,
                               snapshot={'review_id': str(item.review_id), 'source_status': item.status}))
    for item in TeacherSamplingItem.objects.exclude(submission__student_id__in=excluded).filter(status__in=['pending', 'claimed', 'needs_correction']).select_related('submission__attempt__student', 'batch', 'result'):
        batch = item.batch
        records.append(_create(item.submission.attempt, 'sampling', f'm6-sample:{item.item_id}', actor=actor, result=item.result,
                               snapshot={'item_id': str(item.item_id), 'batch_id': str(batch.batch_id),
                                         'source_status': item.status, 'selection_reason': item.selection_reason,
                                         'sample_size': batch.sample_size, 'high_risk_size': batch.high_risk_size,
                                         'basis': batch.basis[:500], 'responsible_id': batch.created_by_id,
                                         'window_start': batch.window_start.isoformat(), 'window_end': batch.window_end.isoformat(),
                                         'deadline': batch.deadline.isoformat(), 'scope': batch.scope}))
    for item in ScoreDispute.objects.exclude(student_id__in=excluded).filter(status__in=['submitted', 'under_review']).select_related('submission__attempt__student', 'result'):
        records.append(_create(item.submission.attempt, 'dispute', f'm6-dispute:{item.dispute_id}', actor=actor, result=item.result,
                               snapshot={'dispute_id': str(item.dispute_id), 'source_status': item.status}))
    return records


def _proof(todo):
    if not todo.retest_id:
        return {'verified': False, 'reason': 'missing_retest'}
    assignment = RetestAssignment.objects.select_related(
        'original_attempt__task', 'original_submission', 'started_attempt__task',
        'completed_submission', 'selected_task',
    ).get(pk=todo.retest_id)
    evidence = retest_payload(assignment)
    completed = assignment.completed_submission
    after_help = bool(todo.handled_at and completed and completed.created_at >= todo.handled_at)
    valid = (assignment.original_attempt_id == todo.attempt_id and assignment.student_id == todo.student_id
             and evidence['binding_valid'] and evidence['outcome'] == 'passed' and after_help)
    return {'verified': bool(valid), 'reason': 'verified' if valid else 'retest_evidence_insufficient',
            'after_intervention': after_help, 'retest': evidence}


def _write_change(todo, *, actor, revision, action, updates, summary='', evidence=None):
    old_owner = todo.owner_id
    changed = TeacherTodo.objects.filter(pk=todo.pk, revision=revision).update(
        **updates, revision=F('revision') + 1, updated_at=timezone.now(),
    )
    if not changed:
        raise OperationsError('revision 冲突，请重新读取待办。', 409)
    todo.refresh_from_db()
    TodoAction.objects.create(todo=todo, revision=todo.revision, action=action, actor=actor,
                              old_owner_id=old_owner, new_owner_id=todo.owner_id,
                              summary=summary[:1000], evidence=evidence or {})
    return todo


@transaction.atomic
def change_todo(todo_id, *, actor, revision, action, summary='', assignee_id=None, retest_id=None):
    require_teacher(actor)
    todo = TeacherTodo.objects.select_related('attempt__student').filter(todo_id=todo_id).first()
    if not todo:
        raise OperationsError('待办不存在。', 404)
    _scope(todo.attempt)
    if todo.revision != revision:
        raise OperationsError('revision 冲突，请重新读取待办。', 409)
    if todo.owner_id and todo.owner_id != actor.pk and not _admin(actor):
        raise OperationsError('只能操作本人认领的待办。', 403)
    updates = {}
    if action == 'claim':
        if todo.owner_id:
            raise OperationsError('待办已被认领。', 409)
        updates = {'owner_id': actor.pk, 'status': 'in_progress'}
    elif action == 'transfer':
        if not todo.owner_id or not summary.strip():
            raise OperationsError('转交须先认领并填写原因。')
        assignee = get_user_model().objects.filter(pk=assignee_id).first()
        if not is_teacher(assignee):
            raise OperationsError('接手人必须是有效教师或管理员。')
        updates = {'owner_id': assignee.pk}
    elif action in ('handle', 'verify'):
        if not todo.owner_id:
            raise OperationsError('请先认领待办。')
        if action == 'handle':
            if not summary.strip():
                raise OperationsError('必须填写处理摘要。')
            updates = {'summary': summary[:1000], 'status': 'pending_verification', 'handled_at': timezone.now(), 'proof': {}}
        elif not todo.handled_at:
            raise OperationsError('请先记录实际处理，再验证复测。')
        if retest_id:
            assignment = RetestAssignment.objects.filter(assignment_id=retest_id).first()
            if not assignment or assignment.original_attempt_id != todo.attempt_id or assignment.student_id != todo.student_id:
                raise OperationsError('复测必须关联同一学生的原尝试。')
            todo.retest = assignment
            updates['retest_id'] = assignment.pk
        if action == 'verify':
            proof = _proof(todo)
            updates.update(proof=proof, status='verified' if proof['verified'] else 'pending_verification')
    else:
        raise OperationsError('未知待办操作。')
    return _write_change(todo, actor=actor, revision=revision, action=action,
                         updates=updates, summary=summary, evidence=updates.get('proof'))


def _source_status(todo):
    sources = {
        'help': (TeacherTicket, 'ticket_id'),
        'manual_review': (ManualReviewTask, 'review_id'),
        'sampling': (TeacherSamplingItem, 'item_id'),
        'dispute': (ScoreDispute, 'dispute_id'),
    }
    model, field = sources.get(todo.kind, (None, None))
    reference = todo.source_snapshot.get(field) if field else None
    if model and reference:
        return model.objects.filter(**{field: reference}).values_list('status', flat=True).first()
    return None


def todo_payload(todo):
    proof = _proof(todo) if todo.status == 'verified' else todo.proof
    status = 'pending_verification' if todo.status == 'verified' and not proof['verified'] else todo.status
    return {'todo_id': str(todo.todo_id), 'kind': todo.kind, 'student_id': todo.student_id,
            'attempt_id': str(todo.attempt.attempt_id), 'proposal_id': todo.proposal_id,
            'original_result_id': str(todo.original_result.result_id) if todo.original_result_id else None,
            'owner_id': todo.owner_id, 'revision': todo.revision, 'status': status, 'stored_status': todo.status,
            'summary': todo.summary, 'source': todo.source_snapshot, 'source_key': todo.source_key,
            'source_current_status': _source_status(todo),
            'retest_id': str(todo.retest.assignment_id) if todo.retest_id else None,
            'proof': proof, 'window': {'start': todo.window_start.isoformat(), 'end': todo.window_end.isoformat()},
            'actions': [{'revision': row.revision, 'action': row.action, 'actor_id': row.actor_id,
                         'old_owner_id': row.old_owner_id, 'new_owner_id': row.new_owner_id,
                         'summary': row.summary, 'created_at': row.created_at.isoformat(), 'evidence': row.evidence}
                        for row in todo.actions.order_by('revision')]}


@transaction.atomic
def consume_notices(*, actor):
    require_teacher(actor)
    receipts = []
    notices = DownstreamNotice.objects.filter(target='module8').exclude(result__student_id__in=excluded_student_ids()).select_related(
        'result__submission', 'result__task', 'result__catalog', 'correction__original_result', 'correction__corrected_result',
    ).order_by('created_at', 'pk')
    for notice in notices:
        existing = ProjectionReceipt.objects.filter(notice_key=notice.notice_key).first()
        if existing:
            receipts.append(existing)
            continue
        result = notice.result
        submission = result.submission
        start, end = _day(submission.created_at)
        affected = TeacherTodo.objects.filter(student_id=result.student_id).filter(
            Q(attempt_id=result.attempt_id) | Q(retest__completed_submission=submission),
        ).select_related('attempt__task', 'attempt__catalog', 'retest')
        scopes = {(result.task.task_key, submission.task_version, result.catalog.version, start, end)}
        for todo in affected:
            scopes.add((todo.attempt.task.task_key, todo.attempt.task_version, todo.attempt.catalog.version, todo.window_start, todo.window_end))
            if todo.status == 'verified':
                proof = _proof(todo)
                if not proof['verified']:
                    _write_change(todo, actor=actor, revision=todo.revision, action='correction_reopened',
                                  updates={'status': 'pending_verification', 'proof': proof}, evidence=proof)
        projections = []
        for task_key, task_version, catalog_version, begin, finish in sorted(scopes):
            data = query_learning(student_id=result.student_id, task_key=task_key, catalog_version=catalog_version,
                                  start=begin, end=finish, excluded_student_ids=excluded_student_ids())
            projections.append({'student_id': result.student_id, 'task_key': task_key, 'task_version': task_version,
                                'catalog_version': catalog_version, 'window': data['window'],
                                'version_groups': [group for group in data['version_groups'] if group['versions']['task_version'] == task_version]})
        current = VerificationResult.objects.get(submission=submission, is_current=True)
        receipt = ProjectionReceipt.objects.create(notice_key=notice.notice_key, payload={
            'student_id': result.student_id, 'notice_result_id': str(result.result_id), 'current_result_id': str(current.result_id),
            'current_version': current.version, 'correction_id': str(notice.correction.correction_id) if notice.correction_id else None,
            'original_result_id': str(notice.correction.original_result.result_id) if notice.correction_id else str(result.result_id),
            'projections': projections, 'source_notice_unchanged': True,
        })
        receipts.append(receipt)
    return receipts
