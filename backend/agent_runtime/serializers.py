from rest_framework import serializers

from .models import AgentRun


class LearningRunRequestSerializer(serializers.Serializer):
    message = serializers.CharField(allow_blank=False, trim_whitespace=True)
    agent_id = serializers.CharField(required=False, default='tutor', allow_blank=False)
    attempt_id = serializers.UUIDField(required=False)
    teaching_run_id = serializers.UUIDField(required=False)
    context = serializers.DictField(required=False, default=dict)
    conversation_history = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )


class AgentRunSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get('fresh_run'):
            # Legacy run snapshots have no source-complete provenance. Retain run
            # identity/status, but never serialize arbitrary nested body/metadata.
            for field in ('plan', 'retrieved_docs', 'used_tools'):
                data[field] = []
            for field in ('intermediate_result', 'verification_result'):
                data[field] = {}
            data['final_result'] = {'content': '[历史内容未能验证材料权限，已隐藏]', 'redacted': True}
            data['error_message'] = ''
        return data

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
