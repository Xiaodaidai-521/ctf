from rest_framework import serializers
from .models import (
    LearningDirection,
    StudentProfile,
    LearningPreference,
    LearningPersona,
)


class LearningDirectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningDirection
        fields = [
            'id', 'key', 'label', 'description', 'sort_order', 'is_active',
        ]


class LearningPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningPreference
        fields = [
            'id', 'profile', 'preferred_pace', 'preferred_modality',
            'prefers_diagrams', 'prefers_code_examples',
            'daily_study_hours', 'difficulty_bias',
        ]


class LearningPersonaSerializer(serializers.ModelSerializer):
    persona_traits = serializers.SerializerMethodField()
    generation_status = serializers.SerializerMethodField()
    generation_provider = serializers.SerializerMethodField()
    input_signature = serializers.SerializerMethodField()

    class Meta:
        model = LearningPersona
        fields = [
            'id', 'profile', 'persona_label', 'confidence_score',
            'persona_traits', 'recommended_agent_roster', 'last_computed',
            'generation_status', 'generation_provider', 'input_signature',
        ]

    def _meta(self, obj):
        traits = obj.persona_traits if isinstance(obj.persona_traits, dict) else {}
        meta = traits.get('_meta') if isinstance(traits, dict) else {}
        return meta if isinstance(meta, dict) else {}

    def get_persona_traits(self, obj):
        traits = dict(obj.persona_traits or {})
        traits.pop('_meta', None)
        return traits

    def get_generation_status(self, obj):
        return self._meta(obj).get('generation_status', '')

    def get_generation_provider(self, obj):
        return self._meta(obj).get('provider', '')

    def get_input_signature(self, obj):
        return self._meta(obj).get('input_signature', '')


class StudentProfileSerializer(serializers.ModelSerializer):
    preference = LearningPreferenceSerializer(read_only=True)
    persona = LearningPersonaSerializer(read_only=True)

    class Meta:
        model = StudentProfile
        fields = [
            'id', 'user', 'learning_goals', 'self_assessed_skills',
            'onboarding_completed', 'preference', 'persona',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class OnboardingSerializer(serializers.Serializer):
    """引导流程专用序列化器——字段名与任务规范对齐"""
    learning_goals = serializers.CharField(required=False, allow_blank=True, default='')
    skills = serializers.JSONField(required=False, default=dict)
    pace = serializers.ChoiceField(
        choices=['self_paced', 'scheduled', 'intensive'],
        default='self_paced',
    )
    modality = serializers.JSONField(required=False, default=list)
    prefers_diagrams = serializers.BooleanField(default=True)
    prefers_code_examples = serializers.BooleanField(default=True)
    daily_hours = serializers.FloatField(default=2, min_value=0)
    difficulty_bias = serializers.FloatField(default=0)
