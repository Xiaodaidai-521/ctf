from rest_framework import serializers

from .models import AgentRun


class LearningRunRequestSerializer(serializers.Serializer):
    message = serializers.CharField(allow_blank=False, trim_whitespace=True)
    agent_id = serializers.CharField(required=False, default='tutor', allow_blank=False)
    context = serializers.DictField(required=False, default=dict)
    conversation_history = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )


class AgentRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentRun
        fields = [
            'id',
            'task_type',
            'status',
            'current_step',
            'plan',
            'retrieved_docs',
            'used_tools',
            'intermediate_result',
            'final_result',
            'verification_result',
            'error_message',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields
