from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count, F
from django.utils import timezone
from django.db import transaction
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
        if self.action == 'create':
            return TheoryQuestionCreateSerializer
        return TheoryQuestionSerializer

    def get_permissions(self):
        # Only admins can create, update, or delete questions.
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]


class PracticeExamViewSet(viewsets.ModelViewSet):
    """瀹炴垬鑰冭瘯瑙嗗浘"""
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = PracticeExam.objects.all()

        exam_status = self.request.query_params.get('status')
        if exam_status:
            queryset = queryset.filter(status=exam_status)

        if self.action == 'questions':
            if ExamRecord.objects.filter(
                user=self.request.user,
                practice_exam__pk=self.kwargs['pk'],
                status__in=['in_progress', 'pending']
            ).exists():
                return queryset

        if not self.request.user.is_staff and not self.request.user.is_teacher:
            queryset = queryset.filter(status='published')

        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return PracticeExamCreateSerializer
        return PracticeExamSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticatedOrReadOnly()]

    @action(detail=True, methods=['post'])
    def generate_questions(self, request, pk=None):
        """Generate practice exam questions by difficulty."""
        exam = self.get_object()

        # 鑾峰彇涓嶅悓闅惧害鐨勯鐩?        from challenges.models import Challenge

        easy_questions = Challenge.objects.filter(difficulty='Easy', is_active=True)
        medium_questions = Challenge.objects.filter(difficulty='Medium', is_active=True)
        hard_questions = Challenge.objects.filter(difficulty='Hard', is_active=True)

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

        # 娓呴櫎鏃ч鐩?        exam.exam_questions.all().delete()

        # 娣诲姞鏂伴鐩?        for challenge, order in all_questions:
            PracticeExamQuestion.objects.create(
                exam=exam,
                challenge=challenge,
                order=order
            )

        return Response({
            'message': '棰樼洰鐢熸垚鎴愬姛',
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

        if self.action == 'questions':
            if ExamRecord.objects.filter(
                user=self.request.user,
                theory_exam__pk=self.kwargs['pk'],
                status='in_progress'
            ).exists():
                return queryset

        if not self.request.user.is_staff and not self.request.user.is_teacher:
            queryset = queryset.filter(status='published')

        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return TheoryExamCreateSerializer
        return TheoryExamSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticatedOrReadOnly()]

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

        serializer = TheoryExamQuestionSerializer(questions, many=True)
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

        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return ExamRecordCreateSerializer
        return ExamRecordSerializer

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
    def submit(self, request, pk=None):
        """鎻愪氦鑰冭瘯"""
        record = self.get_object()

        if record.status == 'completed':
            return Response({'error': '鑰冭瘯宸插畬鎴愶紝涓嶈兘閲嶅鎻愪氦'}, status=400)

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

        if record.theory_exam and record.theory_exam.title.startswith('缁煎悎鑰冭瘯-鐞嗚閮ㄥ垎-'):
            suffix = record.theory_exam.title.replace('缁煎悎鑰冭瘯-鐞嗚閮ㄥ垎-', '', 1)
            practice_record = ExamRecord.objects.filter(
                user=record.user,
                exam_type='practice',
                status='pending',
                practice_exam__title=f'缁煎悎鑰冭瘯-瀹炴垬閮ㄥ垎-{suffix}',
            ).first()
            if practice_record:
                practice_record.status = 'in_progress'
                practice_record.save(update_fields=['status'])

        serializer = ExamRecordSerializer(record)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def answer(self, request, pk=None):
        """鎻愪氦鍗曚釜绛旀"""
        record = self.get_object()

        if record.status == 'completed':
            return Response({'error': '鑰冭瘯宸插畬鎴愶紝涓嶈兘鎻愪氦绛旀'}, status=400)

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

            if question.question_type == 'single_choice':
                is_correct = user_answer == question.correct_answer
            elif question.question_type == 'multiple_choice':
                # 澶氶€夌瓟妗堢敤閫楀彿鍒嗛殧锛岄渶瑕佹帓搴忓悗姣旇緝
                user_answers = sorted([a.strip() for a in user_answer.split(',')])
                correct_answers = sorted([a.strip() for a in question.correct_answer.split(',')])
                is_correct = user_answers == correct_answers
            elif question.question_type == 'true_false':
                is_correct = user_answer.lower() == question.correct_answer.lower()

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
            is_correct = check_flag(flag, practice_q.challenge.flag)

            if is_correct:
                points_earned = practice_q.challenge.score
                Submission.objects.create(
                    challenge=practice_q.challenge,
                    user=request.user,
                    flag=flag,
                    is_correct=True
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
            'answer_id': exam_answer.id
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
        """Start a comprehensive theory and practice exam."""
        user = request.user

        # 妫€鏌ユ槸鍚︽湁杩涜涓殑鑰冭瘯
        ongoing_exam = ExamRecord.objects.filter(
            user=user,
            status='in_progress'
        ).first()

        if ongoing_exam:
            # 妫€鏌ユ槸鍚﹁鏀惧純褰撳墠鑰冭瘯
            abandon = request.data.get('abandon', False)
            if not abandon:
                return Response({
                    'error': 'You already have an exam in progress. Finish or abandon it first.',
                    'exam_record_id': ongoing_exam.id
                }, status=400)
            else:
                # 鏀惧純褰撳墠鑰冭瘯
                ongoing_exam.status = 'abandoned'
                ongoing_exam.save()
                return Response({
                    'message': '宸叉斁寮冨綋鍓嶈€冭瘯锛屽彲浠ュ紑濮嬫柊鐨勮€冭瘯'
                })

        with transaction.atomic():
            # 1. 鐞嗚閮ㄥ垎锛氶殢鏈烘娊鍙栭鐩?            # 鑾峰彇鍚勭被棰樼洰
            single_choice_qs = TheoryQuestion.objects.filter(
                question_type='single_choice',
                is_active=True
            )
            multiple_choice_qs = TheoryQuestion.objects.filter(
                question_type='multiple_choice',
                is_active=True
            )
            true_false_qs = TheoryQuestion.objects.filter(
                question_type='true_false',
                is_active=True
            )

            # 妫€鏌ラ搴撴槸鍚︽湁瓒冲棰樼洰
            if single_choice_qs.count() < 30:
                return Response({'error': '鍗曢€夐搴撲笉瓒?0閬擄紝鏃犳硶缁勫嵎'}, status=400)
            if multiple_choice_qs.count() < 20:
                return Response({'error': '澶氶€夐搴撲笉瓒?0閬擄紝鏃犳硶缁勫嵎'}, status=400)
            if true_false_qs.count() < 20:
                return Response({'error': '鍒ゆ柇棰樺簱涓嶈冻20閬擄紝鏃犳硶缁勫嵎'}, status=400)

            # 闅忔満鎶藉彇鐞嗚棰?            selected_single = random.sample(list(single_choice_qs), 30)
            selected_multiple = random.sample(list(multiple_choice_qs), 20)
            selected_true_false = random.sample(list(true_false_qs), 20)

            # 鍒涘缓鐞嗚鑰冭瘯
            theory_exam = TheoryExam.objects.create(
                title=f"缁煎悎鑰冭瘯-鐞嗚閮ㄥ垎-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                description="鑷姩鐢熸垚鐨勭悊璁鸿€冭瘯",
                duration=180,  # 3灏忔椂
                total_points=120,  # 鍗曢€?鍒?30=60锛屽閫?鍒?20=40锛屽垽鏂?鍒?20=20
                pass_score=72,  # 60%鍙婃牸
                status='draft',
                random_order=True,
                created_by=user
            )

            # 娣诲姞鐞嗚棰樼洰
            theory_questions = []
            order = 0
            for q in selected_single:
                theory_questions.append(TheoryExamQuestion(
                    exam=theory_exam, question=q, order=order, points=2
                ))
                order += 1
            for q in selected_multiple:
                theory_questions.append(TheoryExamQuestion(
                    exam=theory_exam, question=q, order=order, points=2
                ))
                order += 1
            for q in selected_true_false:
                theory_questions.append(TheoryExamQuestion(
                    exam=theory_exam, question=q, order=order, points=1
                ))
                order += 1

            TheoryExamQuestion.objects.bulk_create(theory_questions)

            # 鍒涘缓鐞嗚鑰冭瘯璁板綍
            theory_record = ExamRecord.objects.create(
                user=user,
                theory_exam=theory_exam,
                exam_type='theory',
                status='in_progress',
                total_points=theory_exam.total_points,
                total_questions=70,
                start_time=timezone.now()
            )

            # 2. 瀹炴垬閮ㄥ垎锛氫粠 Challenge 鎶藉彇棰樼洰
            from challenges.models import Challenge

            easy_challenges = Challenge.objects.filter(difficulty='easy', is_active=True)
            medium_challenges = Challenge.objects.filter(difficulty='medium', is_active=True)
            hard_challenges = Challenge.objects.filter(difficulty='hard', is_active=True)

            # 妫€鏌ラ搴撴槸鍚︽湁瓒冲棰樼洰
            if easy_challenges.count() < 3:
                return Response({'error': '绠€鍗曢鐩笉瓒?閬擄紝鏃犳硶缁勫嵎'}, status=400)
            if medium_challenges.count() < 2:
                return Response({'error': '涓瓑棰樼洰涓嶈冻2閬擄紝鏃犳硶缁勫嵎'}, status=400)
            if hard_challenges.count() < 1:
                return Response({'error': '鍥伴毦棰樼洰涓嶈冻1閬擄紝鏃犳硶缁勫嵎'}, status=400)

            # 闅忔満鎶藉彇瀹炴垬棰?            selected_easy = random.sample(list(easy_challenges), 3)
            selected_medium = random.sample(list(medium_challenges), 2)
            selected_hard = random.sample(list(hard_challenges), 1)
            selected_practice = selected_easy + selected_medium + selected_hard
            practice_total_points = sum(challenge.score for challenge in selected_practice)

            # 鍒涘缓瀹炴垬鑰冭瘯
            practice_exam = PracticeExam.objects.create(
                title=f"缁煎悎鑰冭瘯-瀹炴垬閮ㄥ垎-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                description="鑷姩鐢熸垚鐨勫疄鎴樿€冭瘯",
                duration=180,  # 3灏忔椂
                easy_count=3,
                medium_count=2,
                hard_count=1,
                total_points=practice_total_points,
                status='draft',
                created_by=user
            )

            # 娣诲姞瀹炴垬棰樼洰
            practice_questions = []
            order = 0
            for q in selected_easy:
                practice_questions.append(PracticeExamQuestion(
                    exam=practice_exam, challenge=q, order=order
                ))
                order += 1
            for q in selected_medium:
                practice_questions.append(PracticeExamQuestion(
                    exam=practice_exam, challenge=q, order=order
                ))
                order += 1
            for q in selected_hard:
                practice_questions.append(PracticeExamQuestion(
                    exam=practice_exam, challenge=q, order=order
                ))
                order += 1

            PracticeExamQuestion.objects.bulk_create(practice_questions)

            # 鍒涘缓瀹炴垬鑰冭瘯璁板綍
            practice_record = ExamRecord.objects.create(
                user=user,
                practice_exam=practice_exam,
                exam_type='practice',
                status='pending',  # 绛夊緟鐞嗚鑰冭瘯瀹屾垚
                total_points=practice_exam.total_points,
                total_questions=6,
                start_time=timezone.now()
            )

            return Response({
                'message': '缁煎悎鑰冭瘯鍒涘缓鎴愬姛',
                'theory_record': {
                    'id': theory_record.id,
                    'exam_id': theory_exam.id,
                    'title': theory_exam.title,
                    'total_questions': 70,  # 30+20+20
                    'duration': theory_exam.duration
                },
                'practice_record': {
                    'id': practice_record.id,
                    'exam_id': practice_exam.id,
                    'title': practice_exam.title,
                    'total_questions': 6,  # 3+2+1
                    'duration': practice_exam.duration
                }
            })
