from django.db import DatabaseError
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from learning_analytics.models import LearningAdjustmentProposal
from learning_map.models import TaskAttempt

from . import operations
from .models import ProjectionReceipt, TeacherTodo
from .permissions import IsTeacher
from .provenance import excluded_student_ids
from .serializers import StrictSerializer, TodoChange, TodoCreate


class OperationsView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    def handle_exception(self, exc):
        if isinstance(exc, DatabaseError):
            return Response({'error': '保存待重试，未确认成功。', 'code': 'save_pending_retry'}, status=503)
        if isinstance(exc, operations.OperationsError):
            return Response({'error': str(exc), 'code': 'revision_conflict' if exc.status_code == 409 else 'operation_rejected'}, status=exc.status_code)
        return super().handle_exception(exc)


class TodoListView(OperationsView):
    def get(self, request):
        StrictSerializer(data=request.query_params).is_valid(raise_exception=True)
        items = TeacherTodo.objects.exclude(student_id__in=excluded_student_ids()).select_related(
            'attempt', 'original_result', 'retest',
        ).prefetch_related('actions').order_by('-updated_at')
        return Response({'groups': {kind: [operations.todo_payload(item) for item in items if item.kind == kind]
                                    for kind, label in TeacherTodo._meta.get_field('kind').choices}})

    def post(self, request):
        serializer = TodoCreate(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        attempt = get_object_or_404(TaskAttempt.objects.select_related('student'), attempt_id=data.pop('attempt_id'))
        proposal_id = data.pop('proposal_id', None)
        proposal = get_object_or_404(LearningAdjustmentProposal, pk=proposal_id) if proposal_id else None
        todo = operations.create_todo(actor=request.user, attempt=attempt, proposal=proposal, **data)
        return Response(operations.todo_payload(todo), status=201)


class TodoChangeView(OperationsView):
    def post(self, request, todo_id):
        serializer = TodoChange(data=request.data)
        serializer.is_valid(raise_exception=True)
        todo = operations.change_todo(todo_id, actor=request.user, **serializer.validated_data)
        return Response(operations.todo_payload(todo))


class TodoSyncView(OperationsView):
    def post(self, request):
        StrictSerializer(data=request.data).is_valid(raise_exception=True)
        items = operations.sync_todos(actor=request.user)
        return Response({'todo_ids': [str(item.todo_id) for item in items]})


class ReceiptView(OperationsView):
    def get(self, request):
        StrictSerializer(data=request.query_params).is_valid(raise_exception=True)
        receipts = ProjectionReceipt.objects.exclude(payload__student_id__in=excluded_student_ids())
        return Response({'receipts': list(receipts.order_by('pk').values('notice_key', 'payload', 'created_at'))})

    def post(self, request):
        StrictSerializer(data=request.data).is_valid(raise_exception=True)
        receipts = operations.consume_notices(actor=request.user)
        return Response({'receipts': [{'notice_key': row.notice_key, 'payload': row.payload} for row in receipts]})
