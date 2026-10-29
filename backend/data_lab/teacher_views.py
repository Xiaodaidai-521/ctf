"""Object-authorized teacher material, deliberately separate from student DTOs."""
from rest_framework.response import Response
from .views import LabView, teacher_case


class TeacherMaterialView(LabView):
    def get(self, request, task_key):
        case = teacher_case(request.user, task_key, request.query_params.get('version'))
        from .teacher_material import TARGETS, NEGATIVES, EXPECTED_REPLAYS, RUBRIC
        return Response({'task_key': task_key, 'task_version': case.task.version,
            'teacher_answer': {'targets': TARGETS[task_key], 'negatives': NEGATIVES[task_key],
                               'replays': EXPECTED_REPLAYS, 'rubric': RUBRIC}})
