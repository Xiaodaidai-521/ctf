from rest_framework import serializers

from .models import TeachingRun


class TeachingRunCreateSerializer(serializers.Serializer):
    attempt_id = serializers.UUIDField()


class TutorRequestSerializer(serializers.Serializer):
    request_id = serializers.CharField(max_length=64)
    message = serializers.CharField(max_length=4000, trim_whitespace=True)
    hint_level = serializers.IntegerField(min_value=1, max_value=4)


class HintRequestSerializer(serializers.Serializer):
    request_id = serializers.CharField(max_length=64)
    level = serializers.IntegerField(min_value=1, max_value=4)
    source = serializers.ChoiceField(choices=['card'], default='card')


class StateVersionSerializer(serializers.Serializer):
    expected_state_version = serializers.IntegerField(min_value=1)


class ResumeSerializer(StateVersionSerializer):
    request_id = serializers.CharField(max_length=64)


class TeacherTicketCreateSerializer(serializers.Serializer):
    question_summary = serializers.CharField(max_length=500)


class TeacherHelpSerializer(serializers.Serializer):
    summary = serializers.CharField(max_length=500)


class PracticeActionSerializer(serializers.Serializer):
    action_id = serializers.CharField(max_length=64)
    action_type = serializers.ChoiceField(choices=['readonly_observation', 'data_export', 'sandbox_execute'])
    payload = serializers.DictField(required=False, default=dict)


class TeachingRunSerializer(serializers.ModelSerializer):
    attempt_id = serializers.UUIDField(source='attempt.attempt_id', read_only=True)
    task_id = serializers.IntegerField(source='attempt.task_id', read_only=True)

    class Meta:
        model = TeachingRun
        fields = [
            'run_id',
            'attempt_id',
            'task_id',
            'mode',
            'state',
            'state_version',
            'context_version',
            'permission_version',
            'hint_level',
            'task_version',
            'catalog_version',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields
