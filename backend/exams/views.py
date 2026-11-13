from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from data_security.adapters.django.protection_status import protection_for
from django.db.models import Q, Count, F
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from datetime import timedelta
from rest_framework.exceptions import ValidationError
from challenges.models import Challenge
from users.permissions import IsAdminRole
import random

from .models import (
    ExamLevelRule, TheoryQuestion, PracticeExam, PracticeExamQuestion,
    TheoryExam, TheoryExamQuestion, ExamRecord, ExamAnswer
)
from .serializers import (
    ExamLevelRuleSerializer,
    TheoryQuestionSerializer, TheoryQuestionCreateSerializer,
    PracticeExamSerializer, PracticeExamCreateSerializer, PracticeExamQuestionSerializer,
    TheoryExamSerializer, TheoryExamCreateSerializer, TheoryExamQuestionSerializer,
    ExamRecordSerializer, ExamRecordCreateSerializer, SubmitAnswerSerializer
)


class ExamLevelRuleViewSet(viewsets.ReadOnlyModelViewSet):
    """鑰冭瘯绛夌骇瑙勫垯"""
    serializer_class = ExamLevelRuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return ExamLevelRule.objects.filter(is_active=True)


class TheoryQuestionViewSet(viewsets.ModelViewSet):
    """鐞嗚棰樼洰瑙嗗浘"""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = TheoryQuestion.objects.filter(is_active=True)

        question_type = self.request.query_params.get('question_type')
        if question_type:
            queryset = queryset.filter(question_type=question_type)

        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        difficulty = self.request.query_params.get('difficulty')
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        # 鎼滅储
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(question_text__icontains=search)

        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return TheoryQuestionCreateSerializer
        return TheoryQuestionSerializer

    def get_permissions(self):
        # Only admins can create, update, or delete questions.
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminRole()]
        return [permissions.IsAuthenticated()]


class PracticeExamViewSet(viewsets.ModelViewSet):
    """瀹炴垬鑰冭瘯瑙嗗浘"""
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = PracticeExam.objects.all()

        exam_status = self.request.query_params.get('status')
        if exam_status:
            queryset = queryset.filter(status=exam_status)

        if self.action in ('questions', 'retrieve') and self.request.user.is_authenticated:
            if ExamRecord.objects.filter(
                user=self.request.user,
                practice_exam__pk=self.kwargs['pk'],
            ).exists():
                return queryset

        if not self.request.user.is_staff and getattr(self.request.user, 'role', None) not in ('teacher', 'admin'):
            queryset = queryset.filter(status='published')

        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return PracticeExamCreateSerializer
        return PracticeExamSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'generate_questions']:
            return [IsAdminRole()]
        return [permissions.IsAuthenticatedOrReadOnly()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def generate_questions(self, request, pk=None):
        """Generate practice exam questions by difficulty."""
        exam = self.get_object()

        easy_questions = Challenge.objects.filter(difficulty='easy', is_active=True)
        medium_questions = Challenge.objects.filter(difficulty='medium', is_active=True)
        hard_questions = Challenge.objects.filter(difficulty='hard', is_active=True)
        if min(exam.easy_count, exam.medium_count, exam.hard_count) < 0:
            raise ValidationError('题目数量不能为负数。')

        # 闅忔満閫夋嫨棰樼洰
        selected_easy = random.sample(list(easy_questions), min(exam.easy_count, easy_questions.count()))
        selected_medium = random.sample(list(medium_questions), min(exam.medium_count, medium_questions.count()))
        selected_hard = random.sample(list(hard_questions), min(exam.hard_count, hard_questions.count()))

        # 鍚堝苟棰樼洰
        all_questions = []
        for idx, q in enumerate(selected_easy):
            all_questions.append((q, idx))
        for idx, q in enumerate(selected_medium, len(selected_easy)):
            all_questions.append((q, idx))
        for idx, q in enumerate(selected_hard, len(selected_easy) + len(selected_medium)):
            all_questions.append((q, idx))

        exam.exam_questions.all().delete()

        for challenge, order in all_questions:
            PracticeExamQuestion.objects.create(
                exam=exam,
                challenge=challenge,
                order=order
            )

        return Response({
            'message': '题目生成成功',
            'total': len(all_questions),
            'easy': len(selected_easy),
            'medium': len(selected_medium),
            'hard': len(selected_hard)
        })

    @action(detail=True, methods=['get'])
    def questions(self, request, pk=None):
        """Return practice exam questions."""
        exam = self.get_object()
        questions = exam.exam_questions.all().order_by('order')
        serializer = PracticeExamQuestionSerializer(questions, many=True)
        return Response(serializer.data)


class TheoryExamViewSet(viewsets.ModelViewSet):
    """鐞嗚鑰冭瘯瑙嗗浘"""
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = TheoryExam.objects.all()

        exam_status = self.request.query_params.get('status')
        if exam_status:
            queryset = queryset.filter(status=exam_status)

        if self.action in ('questions', 'retrieve') and self.request.user.is_authenticated:
            if ExamRecord.objects.filter(
                user=self.request.user,
                theory_exam__pk=self.kwargs['pk'],
            ).exists():
                return queryset

        if not self.request.user.is_staff and getattr(self.request.user, 'role', None) not in ('teacher', 'admin'):
            queryset = queryset.filter(status='published')

        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return TheoryExamCreateSerializer
        return TheoryExamSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminRole()]
        if self.action == 'history':
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticatedOrReadOnly()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['get'])
    def questions(self, request, pk=None):
        """Return theory exam questions."""
        exam = self.get_object()
        questions = exam.exam_questions.all()

        # 闅忔満鎺掑簭
        if exam.random_order:
            questions = list(questions)
            random.shuffle(questions)
        else:
            questions = questions.order_by('order')

        serializer = TheoryExamQuestionSerializer(questions, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """鑾峰彇鎴戠殑鑰冭瘯鍘嗗彶"""
        exam = self.get_object()
        records = ExamRecord.objects.filter(
            user=request.user,
            theory_exam=exam,
            status='completed'
        ).order_by('-created_at')

        return Response({
            'total': records.count(),
            'records': ExamRecordSerializer(records, many=True).data
        })


class ExamRecordViewSet(viewsets.ModelViewSet):
    """鑰冭瘯璁板綍瑙嗗浘"""
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    @staticmethod
    def _normalized_score(record):
        if record.score is None:
            return 0
        total_points = float(record.total_points or 100)
        if total_points <= 0:
            total_points = 100
        percent = float(record.score) / total_points * 100
        return round(max(0, min(percent, 100)), 2)

    def get_queryset(self):
        queryset = ExamRecord.objects.filter(user=self.request.user)

        exam_type = self.request.query_params.get('exam_type')
        if exam_type:
            queryset = queryset.filter(exam_type=exam_type)

        record_status = self.request.query_params.get('status')
        if record_status:
            queryset = queryset.filter(status=record_status)

        if self.action in ('submit', 'answer'):
            queryset = queryset.select_for_update()

        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return ExamRecordCreateSerializer
        return ExamRecordSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def my_history(self, request):
        """鑾峰彇鎴戠殑鑰冭瘯鍘嗗彶"""
        records = ExamRecord.objects.filter(
            user=request.user
        ).order_by('-created_at')

        return Response({
            'total': records.count(),
            'records': ExamRecordSerializer(records, many=True).data
        })

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """鑾峰彇鎴戠殑鑰冭瘯缁熻"""
        records = ExamRecord.objects.filter(user=request.user, status='completed')
        normalized_scores = [self._normalized_score(record) for record in records]

        stats = {
            'total_exams': records.count(),
            'theory_exams': records.filter(exam_type='theory').count(),
            'practice_exams': records.filter(exam_type='practice').count(),
            'passed_exams': records.filter(is_passed=True).count(),
            'average_score': round(sum(normalized_scores) / len(normalized_scores), 2) if normalized_scores else 0,
            'best_score': max(normalized_scores) if normalized_scores else 0,
        }

        return Response(stats)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def submit(self, request, pk=None):
        """鎻愪氦鑰冭瘯"""
        record = self.get_object()

        if record.status != 'in_progress':
            return Response({'error': '考试当前未进行，不能提交。'}, status=400)

        if record.user != request.user:
            return Response({'error': '鏃犳潈鎻愪氦姝よ€冭瘯'}, status=403)

        # 璁＄畻鍒嗘暟
        answers = record.answers.all()
        total_points = 0
        correct_count = 0

        for answer in answers:
            total_points += float(answer.points_earned)
            if answer.is_correct:
                correct_count += 1

        record.score = total_points
        record.correct_count = correct_count
        record.status = 'completed'
        record.end_time = timezone.now()
        record.time_spent = int((record.end_time - record.start_time).total_seconds())

        # 鍒ゆ柇鏄惁閫氳繃
        if record.theory_exam:
            record.is_passed = record.score >= record.theory_exam.pass_score

        record.save()

        normalized_score = 0
        if record.total_points:
            normalized_score = round(float(record.score) / record.total_points * 100, 2)
        from learning_analytics.events import record_learning_event
        record_learning_event(request.user, 'exam_submitted', {
            'exam_record_id': record.id,
            'exam_type': record.exam_type,
            'normalized_score': normalized_score,
            'passed': bool(record.is_passed),
        })

        if record.theory_exam and record.theory_exam.title.startswith('综合考试-理论部分-'):
            suffix = record.theory_exam.title.replace('综合考试-理论部分-', '', 1)
            practice_record = ExamRecord.objects.filter(
                user=record.user,
                exam_type='practice',
                status='pending',
                practice_exam__title=f'综合考试-实战部分-{suffix}',
            ).first()
            if practice_record:
                practice_record.status = 'in_progress'
                practice_record.save(update_fields=['status'])

        serializer = ExamRecordSerializer(record)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def answer(self, request, pk=None):
        """鎻愪氦鍗曚釜绛旀"""
        record = self.get_object()

        if record.status != 'in_progress':
            return Response({'error': '考试当前未进行，不能提交答案。'}, status=400)

        exam = record.theory_exam or record.practice_exam
        if exam is None or exam.duration <= 0:
            return Response({'error': '考试时限配置不可用。'}, status=400)
        if timezone.now() >= record.start_time + timedelta(minutes=exam.duration):
            return Response({'error': '考试时间已结束，不能提交新的答案，请交卷结算。', 'code': 'exam_time_expired'}, status=400)

        if record.user != request.user:
            return Response({'error': 'No permission to submit answers for this exam'}, status=403)

        serializer = SubmitAnswerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        data = serializer.validated_data
        if data.get('exam_record_id') != record.id:
            return Response({'error': 'exam_record_id does not match the requested record'}, status=400)

        # 鍒ゆ柇绛旀鏄惁姝ｇ‘
        is_correct = False
        points_earned = 0

        if data.get('theory_question_id'):
            exam_question = TheoryExamQuestion.objects.filter(
                exam=record.theory_exam,
                question_id=data['theory_question_id'],
            ).select_related('question').first()
            if not exam_question:
                return Response({'error': 'Question does not belong to this exam'}, status=400)
            question = exam_question.question
            user_answer = data['user_answer'].strip()
            correct_answer = question.read_protected('correct_answer')

            if question.question_type == 'single_choice':
                is_correct = user_answer == correct_answer
            elif question.question_type == 'multiple_choice':
                # 澶氶€夌瓟妗堢敤閫楀彿鍒嗛殧锛岄渶瑕佹帓搴忓悗姣旇緝
                user_answers = sorted([a.strip() for a in user_answer.split(',')])
                correct_answers = sorted([a.strip() for a in correct_answer.split(',')])
                is_correct = user_answers == correct_answers
            elif question.question_type == 'true_false':
                is_correct = user_answer.lower() == correct_answer.lower()

            points_earned = exam_question.points if is_correct else 0

        elif data.get('practice_question_id'):
            # 瀹炴垬棰橀渶瑕佹彁浜lag
            practice_q = PracticeExamQuestion.objects.filter(
                exam=record.practice_exam,
                id=data['practice_question_id'],
            ).select_related('challenge').first()
            if not practice_q:
                return Response({'error': 'Question does not belong to this exam'}, status=400)
            from submissions.models import Submission
            from challenges.utils import check_flag

            flag = data['user_answer'].strip()
            is_correct = check_flag(flag, practice_q.challenge.read_protected('flag'))

            if is_correct:
                points_earned = practice_q.challenge.score
                Submission.objects.create(
                    challenge=practice_q.challenge,
                    user=request.user,
                    flag=flag,
                    is_correct=True,
                    ip_address=request.META.get('REMOTE_ADDR') or '127.0.0.1',
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )

        exam_answer, created = ExamAnswer.objects.update_or_create(
            exam_record=record,
            theory_question_id=data.get('theory_question_id'),
            practice_question_id=data.get('practice_question_id'),
            defaults={
                'user_answer': data['user_answer'],
                'is_correct': is_correct,
                'points_earned': points_earned,
                'time_spent': data.get('time_spent', 0)
            }
        )

        return Response({
            'is_correct': is_correct,
            'points_earned': points_earned,
            'answer_id': exam_answer.id,
            'protection': protection_for(exam_answer),
        })

    @action(detail=True, methods=['get'])
    def result(self, request, pk=None):
        """鑾峰彇鑰冭瘯缁撴灉"""
        record = self.get_object()

        if record.user != request.user:
            return Response({'error': '鏃犳潈鏌ョ湅姝よ€冭瘯缁撴灉'}, status=403)

        serializer = ExamRecordSerializer(record)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def score_trend(self, request):
        """Return score trend grouped by completed exam date."""
        records = ExamRecord.objects.filter(
            user=request.user,
            status='completed'
        ).order_by('created_at')

        def avg(values):
            return round(sum(values) / len(values), 2) if values else None

        grouped = {}
        for record in records:
            date_label = timezone.localtime(record.created_at).strftime('%m-%d')
            grouped.setdefault(date_label, {'theory': [], 'practice': [], 'total': []})
            score = self._normalized_score(record)
            grouped[date_label]['total'].append(score)
            if record.exam_type == 'theory':
                grouped[date_label]['theory'].append(score)
            elif record.exam_type == 'practice':
                grouped[date_label]['practice'].append(score)

        dates = list(grouped.keys())

        return Response({
            'dates': dates,
            'scores': [avg(grouped[date]['total']) for date in dates],
            'theory_scores': [avg(grouped[date]['theory']) for date in dates],
            'practice_scores': [avg(grouped[date]['practice']) for date in dates]
        })

    @action(detail=False, methods=['post'])
    def start_comprehensive_exam(self, request):
        from .comprehensive import start_comprehensive
        return start_comprehensive(request)
