from django.db import DatabaseError, transaction
from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from learning_map.models import TaskAttempt
from learning_map.views import ClaimTaskView
from . import services, replay
from .catalog import CASES, NOTICE, case_spec, digest, student_material
from .common import (Conflict, SavePending, basis_cards, check_payload, emit, own_lab,
                     require_material, teacher_allowed)
from .models import CasePackage, LabAttempt


class LabView(APIView):
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, DatabaseError):
            exc = SavePending()
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store, private'
        response['Vary'] = 'Cookie, Authorization'
        return response


def get_case(task_key, version=None):
    query = CasePackage.objects.select_related('task__catalog', 'owner').filter(task__task_key=task_key)
    if version:
        query = query.filter(task__version=version)
    case = query.first()
    if case is None:
        raise NotFound()
    return case


def teacher_case(user, task_key, version=None):
    case = get_case(task_key, version)
    if not teacher_allowed(user, case):
        raise NotFound()
    return case


class CasesView(LabView):
    def get(self, request):
        return Response({'notice': NOTICE, 'cases': [dict(task_key=c.task.task_key, task_version=c.task.version,
            title=c.task.title, status=c.status, paused=c.paused, withdrawn=c.withdrawn)
            for c in CasePackage.objects.select_related('task').filter(task__task_key__in=CASES)],
            'attempts': [dict(attempt_id=str(lab.attempt.attempt_id), task_key=lab.case.task.task_key)
                for lab in LabAttempt.objects.select_related('attempt', 'case__task').filter(attempt__student=request.user)]})


class CaseView(LabView):
    def get(self, request, task_key):
        case = get_case(task_key, request.query_params.get('version'))
        if not LabAttempt.objects.filter(case=case, attempt__student=request.user).exists():
            raise NotFound()
        require_material(case)
        return Response({**student_material(task_key), 'basis_cards': basis_cards(case)})


class ClaimView(LabView):
    @transaction.atomic
    def post(self, request, task_key):
        check_payload(request.data, ('version',))
        case = get_case(task_key)
        case = CasePackage.objects.select_for_update().select_related('task__catalog').get(pk=case.pk)
        require_material(case, claiming=True)
        if case.task.purpose == 'retest':
            raise Conflict('复测须从模块六分配领取，不能普通重做替代。')
        result = ClaimTaskView().post(request, case.task_id)
        if result.status_code >= 400:
            return result
        attempt = TaskAttempt.objects.get(attempt_id=result.data['attempt_id'], student=request.user)
        lab, created = LabAttempt.objects.get_or_create(attempt=attempt, defaults={'case': case})
        if created:
            emit(lab, 'claim', attempt.attempt_id, case.material_digest, event_type='task_claim')
        return Response({'attempt_id': str(attempt.attempt_id), 'created': created}, status=201 if created else 200)


class AttemptView(LabView):
    def get(self, request, attempt_id):
        lab = own_lab(request.user, attempt_id)
        return Response({'attempt_id': str(attempt_id), 'material': student_material(lab.case.task.task_key),
            'basis_cards': basis_cards(lab.case), 'basis': lab.basis, 'revision': lab.revision,
            'scan': services.scan_dto(lab.active_scan) if lab.active_scan else None,
            'replays': [replay.replay_dto(r) for r in lab.replays.order_by('created_at')],
            'submissions': [str(s.submission_id) for s in lab.submissions.order_by('created_at')]})

    @transaction.atomic
    def post(self, request, attempt_id):
        check_payload(request.data, ())
        try:
            attempt = TaskAttempt.objects.select_related('task__catalog', 'student').get(attempt_id=attempt_id, student=request.user)
        except TaskAttempt.DoesNotExist:
            raise NotFound() from None
        case = get_case(attempt.task.task_key, attempt.task_version)
        require_material(case, claiming=not LabAttempt.objects.filter(attempt=attempt).exists())
        if attempt.task_id != case.task_id:
            raise NotFound()
        if attempt.task.purpose == 'retest':
            from skill_review.models import RetestAssignment
            if not RetestAssignment.objects.filter(started_attempt=attempt, student=request.user).exists():
                raise Conflict('缺少模块六新场景复测分配。')
        lab, created = LabAttempt.objects.get_or_create(attempt=attempt, defaults={'case': case})
        if created:
            emit(lab, 'open', attempt_id, case.material_digest)
        return Response({'attempt_id': str(attempt_id), 'created': created})


class BasisView(LabView):
    def post(self, request, attempt_id):
        lab = services.save_basis(request.user, attempt_id, request.data)
        return Response({'save_status': 'saved', 'basis_digest': lab.basis_digest, 'revision': lab.revision})


class ScansView(LabView):
    def post(self, request, attempt_id):
        return Response(services.scan_dto(services.start_scan(request.user, attempt_id, request.data)))


class ScanView(LabView):
    def get(self, request, scan_id):
        scan = services.owned_scan(request.user, scan_id)
        try:
            offset, limit = int(request.query_params.get('offset', 0)), int(request.query_params.get('limit', 50))
        except ValueError:
            raise ValidationError('分页参数必须为整数。') from None
        return Response(services.scan_dto(scan, offset=offset, limit=limit))


class ReviewsView(LabView):
    def post(self, request, profile_id):
        return Response(services.submit_review(request.user, profile_id, request.data))


class ReplaysView(LabView):
    def post(self, request, attempt_id):
        return Response(replay.replay_dto(replay.start_replay(request.user, attempt_id, request.data)))


class ReplayView(LabView):
    def get(self, request, replay_id):
        return Response(replay.replay_dto(replay.owned_replay(request.user, replay_id)))

    def post(self, request, replay_id):
        return Response(replay.replay_dto(replay.save_judgment(request.user, replay_id, request.data)))


class SubmissionsView(LabView):
    def post(self, request, attempt_id):
        from .submissions import submit, submission_dto
        return Response(submission_dto(submit(request.user, attempt_id, request.data)))


class SubmissionView(LabView):
    def get(self, request, submission_id):
        from .submissions import owned_submission, submission_dto
        return Response(submission_dto(owned_submission(request.user, submission_id)))

    def post(self, request, submission_id):
        from .submissions import owned_submission, deliver, submission_dto
        check_payload(request.data, ())
        return Response(submission_dto(deliver(owned_submission(request.user, submission_id))))


class HelpView(LabView):
    def post(self, request, attempt_id):
        from .help import request_help
        return Response(request_help(request.user, attempt_id, request.data))


class HelpDisplayView(LabView):
    def post(self, request, request_id):
        from .help import display_help
        check_payload(request.data, ())
        return Response(display_help(request.user, request_id))


class AnalysisView(LabView):
    def get(self, request, attempt_id):
        from .help import analysis
        return Response(analysis(request.user, attempt_id))


class TeacherCasesView(LabView):
    def get(self, request):
        return Response({'cases': [dict(task_key=c.task.task_key, title=c.task.title, status=c.status)
            for c in CasePackage.objects.select_related('task') if teacher_allowed(request.user, c)]})


class TeacherCaseView(LabView):
    def get(self, request, task_key):
        case = teacher_case(request.user, task_key, request.query_params.get('version'))
        return Response({'material': student_material(task_key), 'status': case.status,
            'paused': case.paused, 'withdrawn': case.withdrawn,
            'author_review': case.author_review, 'second_review': case.second_review, 'release_checks': case.release_checks,
            'attempts': [dict(attempt_id=str(lab.attempt.attempt_id), student_id=lab.attempt.student_id,
                submissions=[dict(submission_id=str(s.submission_id), status=s.status,
                    failure_code=s.failure_code, module6_id=str(s.module6.submission_id) if s.module6 else None)
                    for s in lab.submissions.select_related('module6')])
                for lab in LabAttempt.objects.select_related('attempt').filter(case=case)]})

    @transaction.atomic
    def post(self, request, task_key):
        case = teacher_case(request.user, task_key)
        check_payload(request.data, ('paused', 'withdrawn'))
        for field, value in request.data.items():
            if type(value) is not bool:
                raise ValidationError('状态必须是布尔值。')
            setattr(case, field, value)
        case.save(update_fields=list(request.data))
        from uuid import uuid4
        from learning_map.services.events import emit_event
        from .common import short_id
        emit_event(user=request.user, event_type='teacher_adjustment', event_id=short_id('case_state', uuid4()),
            catalog=case.task.catalog, task=case.task,
            extra={'source': 'data_lab', 'action': 'case_state', 'paused': case.paused, 'withdrawn': case.withdrawn})
        return Response({'paused': case.paused, 'withdrawn': case.withdrawn})


class TeacherHelpView(LabView):
    def post(self, request, task_key, attempt_id):
        from .help import teacher_help
        return Response(teacher_help(request.user, teacher_case(request.user, task_key), attempt_id, request.data))
