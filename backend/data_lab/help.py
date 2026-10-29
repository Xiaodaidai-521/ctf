"""Version-bound assistance facts; static cards work without any model service."""
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from skill_review.models import AssistanceRecord
from .catalog import case_spec, digest
from .common import (Conflict, assert_same, cas_lab, check_payload, emit, key,
                     own_lab, short_id, teacher_allowed, text)
from .models import HelpRequest


def request_dto(request):
    return {'request_id': str(request.request_id), 'level': request.record.level,
            'source': request.record.source, 'shown': request.record.shown}


@transaction.atomic
def request_help(user, attempt_id, data):
    check_payload(data, ('level', 'source', 'idempotency_key'), ('level', 'source', 'idempotency_key'))
    lab = own_lab(user, attempt_id, lock=True)
    operation_key = key(data)
    existing = lab.help_requests.filter(idempotency_key=operation_key).select_related('record').first()
    if existing:
        return request_dto(assert_same(existing, data))
    if type(data['level']) is not int or data['level'] not in range(1, 5):
        raise ValidationError('提示层级必须是1—4。')
    if data['source'] != 'card':
        raise ValidationError('本实验台使用预置卡片；没有生成式提示入口。')
    level = data['level']
    shown = set(AssistanceRecord.objects.filter(attempt=lab.attempt, kind='hint', shown=True).values_list('level', flat=True))
    if not set(range(1, level)).issubset(shown):
        raise Conflict('请先查看前一层提示，再按需展开。')
    cas_lab(lab)
    spec = case_spec(lab.case.task.task_key)
    record = AssistanceRecord.objects.create(event_id=short_id('help', attempt_id, operation_key),
        student=user, attempt=lab.attempt, task=lab.attempt.task, kind='hint', level=level,
        source='card', requested_at=timezone.now(), created_by=user,
        content_ref=f"data-lab:{spec['material_version']}:hint:{level}")
    request = HelpRequest.objects.create(lab=lab, record=record, idempotency_key=operation_key,
        request_digest=digest(data), material_version=spec['material_version'])
    emit(lab, 'hint_request', request.request_id, request.request_digest, event_type='hint_request', level=level, source='card')
    return request_dto(request)


@transaction.atomic
def display_help(user, request_id):
    request = HelpRequest.objects.select_related('record', 'lab__attempt').filter(
        request_id=request_id, lab__attempt__student=user).first()
    if request is None:
        raise NotFound()
    lab = own_lab(user, request.lab.attempt.attempt_id, lock=True)
    spec = case_spec(lab.case.task.task_key)
    if request.material_version != spec['material_version']:
        raise Conflict('提示材料版本已变化。')
    record = AssistanceRecord.objects.select_for_update().get(pk=request.record_id)
    if not record.shown:
        cas_lab(lab)
        record.shown, record.shown_at = True, timezone.now()
        record.save(update_fields=['shown', 'shown_at'])
        emit(lab, 'hint_show', request.request_id, request.request_digest,
             event_type='hint_show', level=record.level, source=record.source, shown=True)
    request.record = record
    return {**request_dto(request), 'content': spec['hints'][record.level - 1]}


@transaction.atomic
def analysis(user, attempt_id):
    lab = own_lab(user, attempt_id, lock=True)
    if not lab.submissions.filter(module6__results__is_current=True,
                                  module6__results__program_status__in=('passed', 'failed')).exists():
        raise Conflict('先提交证据并完成程序核验交接，才可查看学生解析。')
    spec = case_spec(lab.case.task.task_key)
    event_id = short_id('analysis', user.pk, lab.attempt.task_id, spec['material_version'])
    record, created = AssistanceRecord.objects.get_or_create(event_id=event_id, defaults={
        'student': user, 'attempt': lab.attempt, 'task': lab.attempt.task,
        'kind': 'analysis_view', 'source': 'card', 'shown': True,
        'requested_at': timezone.now(), 'shown_at': timezone.now(), 'created_by': user,
        'content_ref': f"data-lab:{spec['material_version']}:analysis"})
    if created:
        cas_lab(lab)
        emit(lab, 'analysis_view', record.record_id, event_type='analysis_view', source='card', shown=True)
    from .teacher_material import STUDENT_EXPLANATION
    return {'content': STUDENT_EXPLANATION[lab.case.task.task_key], 'answer_exposure': True}


@transaction.atomic
def teacher_help(user, case, attempt_id, data):
    if not teacher_allowed(user, case):
        raise NotFound()
    check_payload(data, ('summary', 'level', 'idempotency_key'), ('summary', 'idempotency_key'))
    from .models import LabAttempt
    target = LabAttempt.objects.select_related('attempt__student').filter(case=case, attempt__attempt_id=attempt_id).first()
    if target is None:
        raise NotFound()
    lab = own_lab(target.attempt.student, attempt_id, lock=True)
    summary = text(data['summary'], 'summary', 1500)
    level = data.get('level', 1)
    if type(level) is not int or level not in range(1, 5):
        raise ValidationError('请记录实际帮助层级1—4。')
    event_id = short_id('teacher_help', user.pk, attempt_id, key(data))
    existing = AssistanceRecord.objects.filter(event_id=event_id).first()
    if existing:
        if existing.note != summary or existing.level != level:
            raise Conflict('同键异内容。')
        return {'record_id': str(existing.record_id), 'shown': True}
    cas_lab(lab)
    record = AssistanceRecord.objects.create(event_id=event_id, student=lab.attempt.student,
        attempt=lab.attempt, task=lab.attempt.task, kind='teacher_help', level=level,
        source='teacher', shown=True, requested_at=timezone.now(), shown_at=timezone.now(),
        created_by=user, note=summary)
    emit(lab, 'teacher_help', record.record_id, digest([user.pk, summary, level]),
         event_type='teacher_help', level=level, source='teacher', shown=True)
    return {'record_id': str(record.record_id), 'shown': True}
