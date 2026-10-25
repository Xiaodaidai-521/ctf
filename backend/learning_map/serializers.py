from rest_framework import serializers

from . import constants
from .models import DeliveryRegisterItem, TaskPackage, TeacherAdjustment


class DiagnosticSubmitSerializer(serializers.Serializer):
    goal_track = serializers.ChoiceField(choices=[constants.TRACK_DATA, constants.TRACK_NETWORK, constants.TRACK_BOTH])
    answers = serializers.DictField(child=serializers.JSONField(), allow_empty=True)
    session_id = serializers.UUIDField(required=False, allow_null=True)


class VerificationFactSerializer(serializers.Serializer):
    fact_id = serializers.CharField(max_length=96)
    student = serializers.IntegerField()
    catalog_version = serializers.CharField(max_length=64)
    capability_id = serializers.CharField(max_length=64)
    knowledge_point_id = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    task_key = serializers.CharField(max_length=80, required=False, allow_blank=True, allow_null=True)
    task_version = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True)
    attempt_id = serializers.UUIDField(required=False, allow_null=True)
    outcome = serializers.ChoiceField(choices=[choice[0] for choice in constants.OUTCOME_CHOICES])
    independence = serializers.ChoiceField(choices=[choice[0] for choice in constants.INDEPENDENCE_CHOICES])
    assistance_level = serializers.IntegerField(required=False, min_value=0, max_value=4, default=0)
    assistance_source = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.ASSISTANCE_SOURCE_CHOICES],
        required=False, default=constants.ASSISTANCE_SOURCE_NONE,
    )
    assistance_shown = serializers.BooleanField(required=False, default=False)
    retest_of_attempt_id = serializers.UUIDField(required=False, allow_null=True)
    first_attempt = serializers.BooleanField(required=False, default=True)
    evidence_ref = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    verifier_version = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    occurred_at = serializers.DateTimeField()
    payload = serializers.DictField(required=False, default=dict)


class AttemptSubmitSerializer(serializers.Serializer):
    submission_snapshot = serializers.DictField(required=False, default=dict)
    evidence_ref = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')


class TeacherAdjustmentSerializer(serializers.Serializer):
    catalog_version = serializers.CharField(max_length=64)
    student = serializers.IntegerField()
    capability_id = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    task_key = serializers.CharField(max_length=80, required=False, allow_blank=True, allow_null=True)
    task_version = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True)
    action = serializers.ChoiceField(choices=[choice[0] for choice in TeacherAdjustment.ACTION_CHOICES])
    rationale = serializers.CharField(allow_blank=False, trim_whitespace=True)
    status = serializers.ChoiceField(choices=['recorded', 'applied', 'withdrawn'], required=False, default='recorded')

    def validate(self, attrs):
        if attrs['action'] == 'assign_task' and not attrs.get('task_key'):
            raise serializers.ValidationError({'task_key': '指定任务时必须填写任务键。'})
        if attrs['action'] in ('assign_task', 'request_retest') and not attrs.get('capability_id'):
            raise serializers.ValidationError({'capability_id': '该动作必须关联能力 ID。'})
        return attrs


class DeliveryRegisterUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryRegisterItem
        fields = [
            'title', 'required_contents', 'version', 'author', 'reviewer',
            'planned_hours', 'due_date', 'status', 'signed_off_at',
            'open_issues', 'attachment_path', 'notes',
        ]
        extra_kwargs = {
            'title': {'required': False},
            'status': {'required': False},
        }

    def validate(self, attrs):
        instance = self.instance
        status_value = attrs.get('status', getattr(instance, 'status', None))
        if status_value == constants.DELIVERY_SIGNED_OFF:
            author = attrs.get('author', getattr(instance, 'author', None))
            reviewer = attrs.get('reviewer', getattr(instance, 'reviewer', None))
            attachment = attrs.get('attachment_path', getattr(instance, 'attachment_path', ''))
            signed_at = attrs.get('signed_off_at', getattr(instance, 'signed_off_at', None))
            missing = []
            if not author:
                missing.append('author')
            if not reviewer:
                missing.append('reviewer')
            if not attachment:
                missing.append('attachment_path')
            if not signed_at:
                missing.append('signed_off_at')
            if missing:
                raise serializers.ValidationError({
                    'status': f'签收缺少字段：{", ".join(missing)}；不得代填审核人。',
                })
        return attrs
