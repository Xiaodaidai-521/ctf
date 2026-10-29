from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from learning_map.models import TaskAttempt

from .metrics import SOURCE_STATUS, metric
from .permissions import IsTeacher, is_teacher
from .projections import attempt_detail, query_learning
from .provenance import excluded_student_ids, formal_students
from .runtime import runtime_summary
from .serializers import LearningQuery, ModeQuery


def query_params(request, serializer_class=LearningQuery):
    serializer = serializer_class(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def learning_scope(request, params):
    if not is_teacher(request.user):
        if request.user.role != 'student' or params['mode'] != 'formal':
            raise PermissionDenied('只允许读取本人的正式学习记录。')
        if params.get('student_id', request.user.pk) != request.user.pk:
            raise PermissionDenied('不能读取其他学生的学习记录。')
        params['student_id'] = request.user.pk
    if params.get('student_id'):
        get_object_or_404(formal_students(), pk=params['student_id'])


def demo_learning():
    versions = {'task_key': 'DEMO-READONLY', 'task_version': 'demo-v1',
                'catalog_version': 'demo-v1', 'event_dictionary': 'v1'}
    return {
        'source': 'demo', 'mode': 'demo', 'status': 'available',
        'updated_at': timezone.now().isoformat(), 'window': {'start': None, 'end': None},
        'notice': '合成演示，不是学生成绩，不进入正式统计。',
        'rows': [{'attempt_id': 'demo-attempt', 'student_id': 'demo-student',
                  'task_title': '合成只读任务', 'versions': versions,
                  'overall_status': 'pending_manual', 'independence': 'assisted', 'source': 'demo'}],
        'version_groups': [{'versions': versions, 'metrics': {
            'pending_manual': metric(1, 1, source='demo', versions=versions),
            'independent_completion': metric(0, 0, 1, source='demo', versions=versions),
        }, 'attempt_ids': ['demo-attempt'], 'retests': []}],
        'source_status': dict(SOURCE_STATUS),
    }


class StudentListView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    def get(self, request):
        params = query_params(request, ModeQuery)
        if params['mode'] == 'demo':
            return Response({'source': 'demo', 'students': [], 'notice': '仅内置合成演示，无真实学生账号。'})
        return Response({'source': 'formal', 'students': list(formal_students().order_by('pk').values('id', 'username'))})


class LearningView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = query_params(request)
        learning_scope(request, params)
        mode = params.pop('mode')
        limit, offset = params.pop('limit'), params.pop('offset')
        if mode == 'demo':
            return Response(demo_learning())
        data = query_learning(**params, excluded_student_ids=excluded_student_ids())
        data['total'] = len(data['rows'])
        data['rows'] = data['rows'][offset:offset + limit]
        data['limit'], data['offset'] = limit, offset
        return Response(data)


class AttemptDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, attempt_id):
        attempt = get_object_or_404(TaskAttempt.objects.exclude(student_id__in=excluded_student_ids()),
                                    attempt_id=attempt_id)
        if not is_teacher(request.user) and (request.user.role != 'student' or attempt.student_id != request.user.pk):
            raise PermissionDenied('不能读取其他学生的尝试明细。')
        return Response(attempt_detail(attempt))


class RuntimeView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    def get(self, request):
        params = query_params(request)
        learning_scope(request, params)
        mode = params.pop('mode')
        limit, offset = params.pop('limit'), params.pop('offset')
        if mode == 'demo':
            return Response({'source': 'demo', 'status': 'no_data', 'records': [], 'version_groups': []})
        data = runtime_summary(**params)
        data['total'] = len(data['records'])
        data['records'] = data['records'][offset:offset + limit]
        return Response(data)
