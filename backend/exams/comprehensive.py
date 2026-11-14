"""Create the two parts together after validating both question pools."""
import random
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response

from challenges.models import Challenge
from .models import ExamRecord, PracticeExam, PracticeExamQuestion, TheoryExam, TheoryExamQuestion, TheoryQuestion
from .pools import gradable_challenges


@transaction.atomic
def start_comprehensive(request):
    user = request.user
    # Starting twice concurrently must not produce two independent active exams.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    ongoing = ExamRecord.objects.filter(user=user, status='in_progress').first()
    if ongoing:
        if request.data.get('abandon') is not True:
            return Response({'error': '已有进行中的考试，请先完成或放弃。', 'exam_record_id': ongoing.pk}, status=400)
        ongoing.status = 'abandoned'
        ongoing.save(update_fields=['status'])
        if ongoing.theory_exam and ongoing.theory_exam.title.startswith('综合考试-理论部分-'):
            suffix = ongoing.theory_exam.title.removeprefix('综合考试-理论部分-')
            ExamRecord.objects.filter(user=user, status='pending', practice_exam__title=f'综合考试-实战部分-{suffix}').update(status='abandoned')
        return Response({'message': '已放弃当前考试，可以开始新的考试。'})

    theory_pools = [
        (list(TheoryQuestion.objects.filter(question_type=kind, is_active=True)), count, points)
        for kind, count, points in (('single_choice', 30, 2), ('multiple_choice', 20, 2), ('true_false', 20, 1))
    ]
    practice_pools = [
        (gradable_challenges(kind), count)
        for kind, count in (('easy', 3), ('medium', 2), ('hard', 1))
    ]
    if any(len(pool) < count for pool, count, _ in theory_pools):
        return Response({'error': '理论题库不足，需要30道单选、20道多选和20道判断题。'}, status=400)
    if any(len(pool) < count for pool, count in practice_pools):
        return Response({'error': '实战题库不足，需要3道简单、2道中等和1道困难题。'}, status=400)

    selected_theory = [(question, points) for pool, count, points in theory_pools for question in random.sample(pool, count)]
    selected_practice = [question for pool, count in practice_pools for question in random.sample(pool, count)]
    suffix = f"{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:12]}"
    theory = TheoryExam.objects.create(
        title=f'综合考试-理论部分-{suffix}', description='自动生成的理论考试',
        duration=180, total_points=120, pass_score=72, status='draft',
        random_order=True, created_by=user,
    )
    TheoryExamQuestion.objects.bulk_create([
        TheoryExamQuestion(exam=theory, question=question, order=index, points=points)
        for index, (question, points) in enumerate(selected_theory)
    ])
    practice = PracticeExam.objects.create(
        title=f'综合考试-实战部分-{suffix}', description='自动生成的实战考试',
        duration=180, easy_count=3, medium_count=2, hard_count=1,
        total_points=sum(question.score for question in selected_practice), status='draft', created_by=user,
    )
    PracticeExamQuestion.objects.bulk_create([
        PracticeExamQuestion(exam=practice, challenge=question, order=index)
        for index, question in enumerate(selected_practice)
    ])
    theory_record = ExamRecord.objects.create(user=user, theory_exam=theory, exam_type='theory', status='in_progress', total_points=theory.total_points, total_questions=len(selected_theory))
    practice_record = ExamRecord.objects.create(user=user, practice_exam=practice, exam_type='practice', status='pending', total_points=practice.total_points, total_questions=len(selected_practice))
    return Response({
        'message': '综合考试创建成功',
        'theory_record': {'id': theory_record.pk, 'exam_id': theory.pk, 'title': theory.title, 'total_questions': len(selected_theory), 'duration': theory.duration},
        'practice_record': {'id': practice_record.pk, 'exam_id': practice.pk, 'title': practice.title, 'total_questions': len(selected_practice), 'duration': practice.duration},
    })
