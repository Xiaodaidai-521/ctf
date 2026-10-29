from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['Unsupported fields; scope is server-controlled.']})
        return super().to_internal_value(data)


class SearchSerializer(StrictSerializer):
    attempt_id = serializers.UUIDField()
    query = serializers.CharField(max_length=500, allow_blank=True, default='')
    request_id = serializers.CharField(max_length=64)
    knowledge_point_ids = serializers.ListField(child=serializers.CharField(max_length=64), max_length=20, required=False)


class IssueSerializer(StrictSerializer):
    attempt_id = serializers.UUIDField()
    request_id = serializers.CharField(max_length=64)
    evidence_id = serializers.UUIDField(required=False)
    reason = serializers.ChoiceField(choices=['insufficient', 'conflict', 'stale', 'unlocated', 'material_error'])


class SourceSerializer(StrictSerializer):
    title = serializers.CharField(max_length=300)
    publisher = serializers.CharField(max_length=200)
    source_url = serializers.URLField(required=False, allow_blank=True)
    source_version = serializers.CharField(max_length=100)
    source_date = serializers.DateField()
    verified_at = serializers.DateField()
    source_snapshot = serializers.CharField(max_length=100000, trim_whitespace=False)
    license_id = serializers.CharField(max_length=100)
    license_url = serializers.URLField(required=False, allow_blank=True)
    attribution_text = serializers.CharField(max_length=1000)
    reuse_scope = serializers.CharField(max_length=200)
    applicability = serializers.CharField(max_length=2000)
    change_note = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    recheck_due_at = serializers.DateTimeField(required=False, allow_null=True)
    conflict_group = serializers.CharField(max_length=100, required=False, allow_blank=True)


class RegisterSerializer(StrictSerializer):
    catalog_version = serializers.CharField(max_length=64)
    task_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=20)
    material_class = serializers.ChoiceField(choices=['lesson', 'hint', 'student_analysis', 'teacher_answer', 'grading_secret'])
    hint_level = serializers.IntegerField(min_value=1, max_value=4, required=False, allow_null=True)
    source_type = serializers.ChoiceField(choices=['teacher_authored', 'article', 'resource', 'knowledge_concept', 'legal_clause'], default='teacher_authored')
    source_object_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    metadata = SourceSerializer()


class ActionSerializer(StrictSerializer):
    expected_revision = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=64)
    reason = serializers.CharField(max_length=500)


class RevisionSerializer(StrictSerializer):
    task_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=20)
    metadata = SourceSerializer()


class GrantSerializer(StrictSerializer):
    catalog_version = serializers.CharField(max_length=64)
    user_id = serializers.IntegerField(min_value=1)
    active = serializers.BooleanField(default=True)
    can_review = serializers.BooleanField(default=False)
    maintain_secrets = serializers.BooleanField(default=False)
