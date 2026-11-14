from rest_framework import serializers
from data_security.adapters.django.protection_status import ProtectionSerializerMixin

from .models import AgentRun, UserMemory


class UserMemorySerializer(ProtectionSerializerMixin, serializers.ModelSerializer):
    def to_representation(self, instance):
        from data_security.contracts import ContractViolation
        result = super().to_representation(instance)
        for name in ('memory_value', 'metadata'):
            try:
                result[name] = instance.display_protected(name)
            except (ContractViolation, RuntimeError, ValueError, TypeError, KeyError):
                result[name] = None
        return result

    class Meta:
        model = UserMemory
        fields = ['id', 'memory_type', 'memory_value', 'metadata', 'created_at', 'updated_at']
        read_only_fields = fields


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
