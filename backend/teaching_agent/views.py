from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_tutoring import TutorRequestConflict, tutor
from .context import resolve_or_create_run, resolve_task_context
from .core_flow import PracticeActionConflict, register_practice_action, task_snapshot
from .events import bounded_event_id, record_teaching_event
from .models import TeacherTicket, TeachingRun
from .serializers import (
    HintRequestSerializer,
    PracticeActionSerializer,
    ResumeSerializer,
    StateVersionSerializer,
    TeacherHelpSerializer,
    TeacherTicketCreateSerializer,
    TutorRequestSerializer,
    TeachingRunCreateSerializer,
    TeachingRunSerializer,
)
from .tutoring_state import (
    IdempotencyConflict,
    StateVersionConflict,
    authorized_analysis,
    display_hint,
    open_teacher_ticket,
    pause_run,
    record_ticket_help,
    request_hint,
    resume_run,
)


class TeachingRunCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TeachingRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run, created = resolve_or_create_run(
            user=request.user,
            attempt_id=serializer.validated_data['attempt_id'],
        )
        if created:
            record_teaching_event(
                student=request.user,
                event_id=bounded_event_id('m2-run-start', run.run_id),
                event_type='teaching_run_started',
                attempt=run.attempt,
                run=run,
                payload={'mode': run.mode},
            )
        context = resolve_task_context(
            user=request.user,
            request_data={'run_id': run.run_id},
            require_attempt=True,
        )
        payload = TeachingRunSerializer(run).data
        payload['task_context'] = context.model_context()
        payload['task_snapshot'] = task_snapshot(context)
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class TeachingRunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        context = resolve_task_context(
            user=request.user,
            request_data={'run_id': run_id},
            require_attempt=True,
        )
        payload = TeachingRunSerializer(context.run).data
        payload['task_context'] = context.model_context()
        payload['task_snapshot'] = task_snapshot(context)
        return Response(payload)


class PracticeActionCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        context = resolve_task_context(
            user=request.user,
            request_data={'run_id': run_id},
            require_attempt=True,
        )
        serializer = PracticeActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            action, created = register_practice_action(
                context=context,
                action_id=data['action_id'],
                action_type=data['action_type'],
                payload=data.get('payload') or {},
            )
        except PracticeActionConflict as exc:
            return Response({'detail': str(exc), 'code': 'action_conflict'}, status=status.HTTP_409_CONFLICT)
        return Response({
            'action_id': action.action_id,
            'action_type': action.action_type,
            'status': action.status,
            'dependency': action.dependency or None,
            'evidence_ref': action.evidence_ref or None,
            'created': created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class TaskTutorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        context = resolve_task_context(user=request.user, request_data={'run_id': run_id}, require_attempt=True)
        serializer = TutorRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            response, tutor_request, created, cache_hit = tutor(
                context=context,
                request_id=data['request_id'],
                message=data['message'],
                hint_level=data['hint_level'],
                provider=getattr(settings, 'TEACHING_AGENT_PROVIDER', 'default'),
            )
        except TutorRequestConflict as exc:
            return Response({'detail': str(exc), 'code': 'tutor_request_conflict'}, status=status.HTTP_409_CONFLICT)
        return Response({
            'request_id': tutor_request.request_id,
            'status': tutor_request.status,
            'response': response,
            'cache_hit': cache_hit,
            'created': created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class HintRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        context = resolve_task_context(user=request.user, request_data={'run_id': run_id}, require_attempt=True)
        serializer = HintRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            delivery, created = request_hint(
                context=context,
                request_id=data['request_id'],
                level=data['level'],
                source=data['source'],
            )
        except IdempotencyConflict as exc:
            return Response({'detail': str(exc), 'code': 'hint_request_conflict'}, status=status.HTTP_409_CONFLICT)
        return Response({
            'request_id': delivery.request_id,
            'record_id': str(delivery.assistance_record.record_id),
            'level': delivery.card.level,
            'source': delivery.source,
            'shown': bool(delivery.displayed_at),
            'created': created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class HintDisplayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id, request_id):
        context = resolve_task_context(user=request.user, request_data={'run_id': run_id}, require_attempt=True)
        delivery, run = display_hint(context=context, request_id=request_id)
        return Response({
            'request_id': delivery.request_id,
            'level': delivery.card.level,
            'title': delivery.card.title,
            'content': delivery.card.content,
            'material_ref': delivery.card.material_ref or None,
            'material_version': delivery.card.version,
            'shown': True,
            'shown_at': delivery.displayed_at.isoformat(),
            'state': run.state,
            'state_version': run.state_version,
        })


class PauseRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        context = resolve_task_context(user=request.user, request_data={'run_id': run_id}, require_attempt=True)
        serializer = StateVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = pause_run(context=context, expected_state_version=serializer.validated_data['expected_state_version'])
        except StateVersionConflict as exc:
            return Response({'detail': str(exc), 'code': 'state_version_conflict'}, status=status.HTTP_409_CONFLICT)
        return Response({'run_id': str(run.run_id), 'state': run.state, 'state_version': run.state_version})


class ResumeRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        context = resolve_task_context(user=request.user, request_data={'run_id': run_id}, require_attempt=True)
        serializer = ResumeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            result, created = resume_run(
                context=context,
                request_id=data['request_id'],
                expected_state_version=data['expected_state_version'],
            )
        except StateVersionConflict as exc:
            return Response({'detail': str(exc), 'code': 'state_version_conflict'}, status=status.HTTP_409_CONFLICT)
        except IdempotencyConflict as exc:
            return Response({'detail': str(exc), 'code': 'resume_request_conflict'}, status=status.HTTP_409_CONFLICT)
        return Response({**result, 'created': created})


class TeacherTicketCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        context = resolve_task_context(user=request.user, request_data={'run_id': run_id}, require_attempt=True)
        serializer = TeacherTicketCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = open_teacher_ticket(context=context, question_summary=serializer.validated_data['question_summary'])
        return Response(_ticket_payload(ticket, teacher=False), status=status.HTTP_201_CREATED)


class TeacherTicketDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id):
        ticket = get_object_or_404(TeacherTicket.objects.select_related('run'), ticket_id=ticket_id)
        teacher = _is_teacher(request.user)
        if ticket.student_id != request.user.id and not teacher:
            raise PermissionDenied('This teacher ticket belongs to another student.')
        return Response(_ticket_payload(ticket, teacher=teacher))


class TeacherTicketHelpView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_id):
        if not _is_teacher(request.user):
            raise PermissionDenied('Teacher role is required.')
        ticket = get_object_or_404(TeacherTicket, ticket_id=ticket_id)
        serializer = TeacherHelpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket, created = record_ticket_help(ticket=ticket, teacher=request.user, summary=serializer.validated_data['summary'])
        return Response({**_ticket_payload(ticket, teacher=True), 'created': created})


class StudentAnalysisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        context = resolve_task_context(user=request.user, request_data={'run_id': run_id}, require_attempt=True)
        analysis = authorized_analysis(context=context)
        response = Response({
            'title': analysis.title,
            'content': analysis.content,
            'content_ref': analysis.content_ref or None,
            'version': analysis.version,
        })
        response['Cache-Control'] = 'private, no-store'
        return response


def _is_teacher(user):
    return bool(getattr(user, 'role', None) in ('teacher', 'admin') or getattr(user, 'is_superuser', False))


def _ticket_payload(ticket, *, teacher):
    payload = {
        'ticket_id': str(ticket.ticket_id),
        'run_id': str(ticket.run.run_id),
        'status': ticket.status,
        'question_summary': ticket.question_summary,
        'created_at': ticket.created_at.isoformat(),
        'helped_at': ticket.helped_at.isoformat() if ticket.helped_at else None,
    }
    if ticket.status == TeacherTicket.STATUS_HELPED:
        payload['actual_help_summary'] = ticket.actual_help_summary
    if teacher:
        payload['student_id'] = ticket.student_id
        payload['attempt_id'] = str(ticket.attempt.attempt_id)
        payload['claimed_by_id'] = ticket.claimed_by_id
    return payload
