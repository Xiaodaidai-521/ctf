from rest_framework import serializers
from .models import GeneratedTutorial, GeneratedQuiz, GeneratedDiagram, GeneratedCodeExercise


class GeneratedTutorialSerializer(serializers.ModelSerializer):
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default=None)
    topic_name = serializers.CharField(source='topic.name', read_only=True, default=None)

    class Meta:
        model = GeneratedTutorial
        fields = [
            'id', 'title', 'content_type', 'content_type_display', 'raw_content',
            'rendered_assets', 'generation_params', 'quality_score', 'reviewer_agent_id',
            'is_approved', 'created_by', 'created_by_name', 'topic', 'topic_name',
            'difficulty', 'difficulty_display', 'prerequisite_concepts',
            'estimated_minutes', 'sections', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'content_type', 'quality_score', 'reviewer_agent_id',
            'is_approved', 'created_at', 'updated_at',
        ]


class GeneratedQuizSerializer(serializers.ModelSerializer):
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default=None)
    topic_name = serializers.CharField(source='topic.name', read_only=True, default=None)

    class Meta:
        model = GeneratedQuiz
        fields = [
            'id', 'title', 'content_type', 'content_type_display', 'raw_content',
            'rendered_assets', 'generation_params', 'quality_score', 'reviewer_agent_id',
            'is_approved', 'created_by', 'created_by_name', 'topic', 'topic_name',
            'difficulty', 'difficulty_display', 'question_count', 'passing_score',
            'questions', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'content_type', 'quality_score', 'reviewer_agent_id',
            'is_approved', 'created_at', 'updated_at',
        ]


class GeneratedDiagramSerializer(serializers.ModelSerializer):
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)
    diagram_type_display = serializers.CharField(source='get_diagram_type_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default=None)
    topic_name = serializers.CharField(source='topic.name', read_only=True, default=None)

    class Meta:
        model = GeneratedDiagram
        fields = [
            'id', 'title', 'content_type', 'content_type_display', 'raw_content',
            'rendered_assets', 'generation_params', 'quality_score', 'reviewer_agent_id',
            'is_approved', 'created_by', 'created_by_name', 'topic', 'topic_name',
            'difficulty', 'difficulty_display', 'diagram_type', 'diagram_type_display',
            'mermaid_code', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'content_type', 'quality_score', 'reviewer_agent_id',
            'is_approved', 'created_at', 'updated_at',
        ]


class GeneratedCodeExerciseSerializer(serializers.ModelSerializer):
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default=None)
    topic_name = serializers.CharField(source='topic.name', read_only=True, default=None)

    class Meta:
        model = GeneratedCodeExercise
        fields = [
            'id', 'title', 'content_type', 'content_type_display', 'raw_content',
            'rendered_assets', 'generation_params', 'quality_score', 'reviewer_agent_id',
            'is_approved', 'created_by', 'created_by_name', 'topic', 'topic_name',
            'difficulty', 'difficulty_display', 'language', 'starter_code',
            'test_cases', 'solution_code', 'hints', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'content_type', 'quality_score', 'reviewer_agent_id',
            'is_approved', 'created_at', 'updated_at',
        ]


# 用于详情和重新生成视图的通用序列化器映射
CONTENT_SERIALIZER_MAP = {
    'tutorial': GeneratedTutorialSerializer,
    'quiz': GeneratedQuizSerializer,
    'diagram': GeneratedDiagramSerializer,
    'exercise': GeneratedCodeExerciseSerializer,
}
