from rest_framework import serializers
from django.utils import timezone

from .models import (
    AdminLearningScore,
    LearningInsight,
    TeachingInterventionPlan,
    WeeklyLearningSummary,
)


class LearningInsightSerializer(serializers.ModelSerializer):
    concept_name = serializers.CharField(source='concept.name', read_only=True, default=None)
    insight_type_display = serializers.CharField(source='get_insight_type_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)

    class Meta:
        model = LearningInsight
        fields = [
            'id', 'student', 'insight_type', 'insight_type_display',
            'concept', 'concept_name', 'title', 'description',
            'severity', 'severity_display', 'actionable', 'action_link',
            'generated_at', 'acknowledged_at'
        ]
        read_only_fields = ['id', 'student', 'generated_at']


class WeeklyLearningSummarySerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.username', read_only=True)

    class Meta:
        model = WeeklyLearningSummary
        fields = [
            'id', 'student', 'student_name', 'week_start',
            'total_study_minutes', 'modules_completed', 'exercises_completed',
            'concepts_mastered', 'ai_interactions', 'sandbox_executions',
            'generated_at'
        ]
        read_only_fields = ['id', 'student', 'generated_at']


class AdminLearningScoreSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.username', read_only=True)
    scored_by_name = serializers.CharField(source='scored_by.username', read_only=True)
    is_ai_eligible = serializers.SerializerMethodField()
    validity_status = serializers.SerializerMethodField()
    validity_reason = serializers.SerializerMethodField()

    class Meta:
        model = AdminLearningScore
        fields = [
            'id', 'student', 'student_name', 'scored_by', 'scored_by_name',
            'measured_at', 'total_score', 'dimension_scores', 'tags', 'remark',
            'is_ai_eligible', 'validity_status', 'validity_reason',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'scored_by', 'created_at', 'updated_at',
            'is_ai_eligible', 'validity_status', 'validity_reason',
        ]

    def validate_measured_at(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError('实际测评日期不能晚于系统当前日期')
        return value

    def validate_total_score(self, value):
        n = float(value)
        if n < 0 or n > 100:
            raise serializers.ValidationError('总分必须在 0 到 100 之间')
        return value

    def validate_dimension_scores(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('分项评分必须是对象')
        for key, score in value.items():
            try:
                n = float(score)
            except (TypeError, ValueError):
                raise serializers.ValidationError(f'{key} 的评分必须是数字')
            if n < 0 or n > 100:
                raise serializers.ValidationError(f'{key} 的评分必须在 0 到 100 之间')
        return value

    def validate_tags(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('评分标签必须是数组')
        return [str(item).strip() for item in value if str(item).strip()]

    def get_is_ai_eligible(self, obj):
        return obj.id in set(self.context.get('eligible_score_ids', []))

    def get_validity_status(self, obj):
        status_map = self.context.get('score_status_map', {})
        return status_map.get(obj.id, {}).get('status', 'unknown')

    def get_validity_reason(self, obj):
        status_map = self.context.get('score_status_map', {})
        return status_map.get(obj.id, {}).get('reason', '')


class TeachingInterventionPlanSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.username', read_only=True)

    class Meta:
        model = TeachingInterventionPlan
        fields = [
            'id', 'student', 'student_name', 'title', 'summary', 'plan_items',
            'source_score_ids', 'self_assessment_snapshot', 'input_snapshot',
            'data_age_days', 'validity_label', 'generated_at',
        ]
        read_only_fields = fields
