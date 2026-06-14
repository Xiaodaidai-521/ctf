from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    ExamLevelRule, TheoryQuestion, PracticeExam, PracticeExamQuestion,
    TheoryExam, TheoryExamQuestion, ExamRecord, ExamAnswer
)

User = get_user_model()


class ExamLevelRuleSerializer(serializers.ModelSerializer):
    minScore = serializers.IntegerField(source='min_score')

    class Meta:
        model = ExamLevelRule
        fields = ['id', 'grade', 'title', 'description', 'minScore', 'sort_order']


class TheoryQuestionSerializer(serializers.ModelSerializer):
    question_type_display = serializers.CharField(source='get_question_type_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)

    class Meta:
        model = TheoryQuestion
        fields = [
            'id', 'question_type', 'question_type_display',
            'category', 'category_display', 'difficulty', 'difficulty_display',
            'question_text', 'options', 'explanation', 'points', 'is_active'
        ]
        read_only_fields = ['created_at', 'updated_at']


class TheoryQuestionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TheoryQuestion
        fields = [
            'question_type', 'category', 'difficulty',
            'question_text', 'options', 'correct_answer', 'explanation', 'points', 'is_active'
        ]


class PracticeExamQuestionSerializer(serializers.ModelSerializer):
    challenge_title = serializers.CharField(source='challenge.title', read_only=True)
    challenge_difficulty = serializers.CharField(source='challenge.difficulty', read_only=True)
    challenge_points = serializers.IntegerField(source='challenge.points', read_only=True)
    challenge_description = serializers.CharField(source='challenge.description', read_only=True)

    class Meta:
        model = PracticeExamQuestion
        fields = [
            'id', 'challenge', 'challenge_title', 'challenge_difficulty',
            'challenge_points', 'challenge_description', 'order'
        ]


class PracticeExamSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    questions_count = serializers.SerializerMethodField()

    class Meta:
        model = PracticeExam
        fields = [
            'id', 'title', 'description', 'status', 'status_display',
            'duration', 'total_points', 'easy_count', 'medium_count', 'hard_count',
            'created_by', 'created_by_name', 'questions_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_questions_count(self, obj):
        return obj.exam_questions.count()


class PracticeExamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PracticeExam
        fields = [
            'title', 'description', 'status',
            'duration', 'total_points', 'easy_count', 'medium_count', 'hard_count'
        ]


class TheoryExamQuestionSerializer(serializers.ModelSerializer):
    question_detail = TheoryQuestionSerializer(source='question', read_only=True)

    class Meta:
        model = TheoryExamQuestion
        fields = ['id', 'question', 'question_detail', 'order', 'points']


class TheoryExamSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    questions_count = serializers.SerializerMethodField()

    class Meta:
        model = TheoryExam
        fields = [
            'id', 'title', 'description', 'status', 'status_display',
            'duration', 'total_points', 'random_order', 'pass_score', 'max_attempts',
            'created_by', 'created_by_name', 'questions_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_questions_count(self, obj):
        return obj.exam_questions.count()


class TheoryExamCreateSerializer(serializers.ModelSerializer):
    question_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = TheoryExam
        fields = [
            'title', 'description', 'status',
            'duration', 'total_points', 'random_order', 'pass_score', 'max_attempts', 'question_ids'
        ]

    def create(self, validated_data):
        question_ids = validated_data.pop('question_ids', [])
        exam = TheoryExam.objects.create(**validated_data)

        # 添加题目到考试
        for idx, question_id in enumerate(question_ids):
            TheoryExamQuestion.objects.create(
                exam=exam,
                question_id=question_id,
                order=idx,
                points=10  # 默认分值
            )

        return exam


class ExamAnswerSerializer(serializers.ModelSerializer):
    question_text = serializers.SerializerMethodField()

    class Meta:
        model = ExamAnswer
        fields = [
            'id', 'theory_question', 'practice_question',
            'user_answer', 'is_correct', 'points_earned', 'time_spent', 'question_text'
        ]

    def get_question_text(self, obj):
        if obj.theory_question:
            return obj.theory_question.question_text
        elif obj.practice_question:
            return obj.practice_question.challenge.title
        return ''


class ExamRecordSerializer(serializers.ModelSerializer):
    exam_type_display = serializers.CharField(source='get_exam_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)
    answers = ExamAnswerSerializer(many=True, read_only=True)
    exam_title = serializers.SerializerMethodField()
    theory_record_id = serializers.SerializerMethodField()
    practice_record_id = serializers.SerializerMethodField()

    class Meta:
        model = ExamRecord
        fields = [
            'id', 'user', 'user_name', 'exam_type', 'exam_type_display',
            'theory_exam', 'practice_exam', 'exam_title', 'status', 'status_display',
            'score', 'total_points', 'correct_count', 'total_questions',
            'start_time', 'end_time', 'time_spent', 'is_passed',
            'answers', 'theory_record_id', 'practice_record_id', 'created_at'
        ]
        read_only_fields = ['start_time', 'created_at']

    def get_exam_title(self, obj):
        if obj.theory_exam:
            return obj.theory_exam.title
        elif obj.practice_exam:
            return obj.practice_exam.title
        return ''

    def _pair_suffix(self, title, prefix):
        if title and title.startswith(prefix):
            return title.replace(prefix, '', 1)
        return None

    def get_theory_record_id(self, obj):
        if not obj.practice_exam:
            return None
        suffix = self._pair_suffix(obj.practice_exam.title, '综合考试-实战部分-')
        if not suffix:
            return None
        record = ExamRecord.objects.filter(
            user=obj.user,
            exam_type='theory',
            theory_exam__title=f'综合考试-理论部分-{suffix}',
        ).order_by('-created_at').first()
        return record.id if record else None

    def get_practice_record_id(self, obj):
        if not obj.theory_exam:
            return None
        suffix = self._pair_suffix(obj.theory_exam.title, '综合考试-理论部分-')
        if not suffix:
            return None
        record = ExamRecord.objects.filter(
            user=obj.user,
            exam_type='practice',
            practice_exam__title=f'综合考试-实战部分-{suffix}',
        ).order_by('-created_at').first()
        return record.id if record else None


class ExamRecordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamRecord
        fields = ['exam_type', 'theory_exam', 'practice_exam']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        validated_data['status'] = 'in_progress'

        # 设置总分和题数
        if validated_data['exam_type'] == 'theory' and validated_data.get('theory_exam'):
            exam = validated_data['theory_exam']
            validated_data['total_points'] = exam.total_points
            validated_data['total_questions'] = exam.exam_questions.count()
        elif validated_data['exam_type'] == 'practice' and validated_data.get('practice_exam'):
            exam = validated_data['practice_exam']
            validated_data['total_points'] = exam.total_points
            validated_data['total_questions'] = exam.exam_questions.count()

        return super().create(validated_data)


class SubmitAnswerSerializer(serializers.Serializer):
    exam_record_id = serializers.IntegerField()
    theory_question_id = serializers.IntegerField(required=False)
    practice_question_id = serializers.IntegerField(required=False)
    user_answer = serializers.CharField()
    time_spent = serializers.IntegerField(default=0)

    def validate(self, data):
        if not data.get('theory_question_id') and not data.get('practice_question_id'):
            raise serializers.ValidationError("必须提供题目ID")
        return data
