from collections.abc import Mapping

from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError('请求必须是对象。')
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({'unknown_fields': sorted(unknown)})
        return super().to_internal_value(data)


class ModeQuery(StrictSerializer):
    mode = serializers.ChoiceField(choices=['formal', 'demo'], default='formal')


class LearningQuery(ModeQuery):
    student_id = serializers.IntegerField(min_value=1, required=False)
    task_key = serializers.CharField(max_length=128, required=False)
    knowledge_point_id = serializers.CharField(max_length=128, required=False)
    catalog_version = serializers.CharField(max_length=64, required=False)
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    limit = serializers.IntegerField(min_value=1, max_value=200, default=100)
    offset = serializers.IntegerField(min_value=0, max_value=100000, default=0)

    def validate(self, attrs):
        if attrs.get('start') and attrs.get('end') and attrs['start'] >= attrs['end']:
            raise serializers.ValidationError('时间窗结束必须晚于开始（左闭右开）。')
        return attrs


class TodoCreate(StrictSerializer):
    attempt_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=['help', 'manual_review', 'sampling', 'dispute', 'evidence'], default='help')
    proposal_id = serializers.IntegerField(min_value=1, required=False)
    summary = serializers.CharField(max_length=1000, required=False, default='', allow_blank=True)


class TodoChange(StrictSerializer):
    revision = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=['claim', 'transfer', 'handle', 'verify'])
    summary = serializers.CharField(max_length=1000, required=False, default='', allow_blank=True)
    assignee_id = serializers.IntegerField(min_value=1, required=False)
    retest_id = serializers.UUIDField(required=False)
