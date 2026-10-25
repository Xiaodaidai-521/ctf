import json
import os

from rest_framework import serializers

from . import constants
from .services import phase3
from .services.workflow import HANDLERS


class EvidenceInputSerializer(serializers.Serializer):
    slot = serializers.CharField(max_length=64)
    ref = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    version = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    summary = serializers.CharField(required=False, allow_blank=True, default='', max_length=4000)
    attachment_id = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.EVIDENCE_STATUS_CHOICES],
        required=False, default=constants.EVIDENCE_STATUS_PROVIDED,
    )
    visibility = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.VISIBILITY_CHOICES],
        required=False, default=constants.VISIBILITY_STUDENT,
    )

    def validate(self, attrs):
        status = attrs.get('status') or constants.EVIDENCE_STATUS_PROVIDED
        if status == constants.EVIDENCE_STATUS_MISSING:
            raise serializers.ValidationError({'status': '不能手工提交“缺失”状态。'})
        has_content = bool(attrs.get('ref') or attrs.get('summary') or attrs.get('attachment_id'))
        if status == constants.EVIDENCE_STATUS_PROVIDED and not has_content:
            raise serializers.ValidationError('已提供证据必须包含引用、摘要或附件。')
        if status in (constants.EVIDENCE_STATUS_UNKNOWN, constants.EVIDENCE_STATUS_NOT_APPLICABLE):
            if not attrs.get('summary'):
                raise serializers.ValidationError('未知/不适用状态必须说明原因。')
        if attrs.get('attachment_id') and not attrs.get('slot'):
            raise serializers.ValidationError({'slot': '附件证据必须指定证据槽。'})
        return attrs


class FeedbackCreateSerializer(serializers.Serializer):
    client_request_id = serializers.CharField(max_length=128)
    student = serializers.IntegerField(required=False, allow_null=True)
    category = serializers.ChoiceField(choices=[choice[0] for choice in constants.CATEGORY_CHOICES])
    issue_type = serializers.CharField(max_length=48)
    catalog_version = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    task_key = serializers.CharField(max_length=80, required=False, allow_blank=True, default='')
    task_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')
    attempt_id = serializers.UUIDField(required=False, allow_null=True)
    attempt_ref = serializers.CharField(max_length=128, required=False, allow_blank=True, default='')
    capability_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    knowledge_point_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    dispute = serializers.CharField(max_length=8000, trim_whitespace=True)
    expected_result = serializers.CharField(max_length=8000, required=False, allow_blank=True, default='')
    reason = serializers.CharField(max_length=8000, required=False, allow_blank=True, default='')
    original_decision_ref = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    original_decision_version = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    original_decision_snapshot = serializers.JSONField(required=False, default=dict)
    evidence = EvidenceInputSerializer(many=True, required=False, default=list)
    involves_actual_execution = serializers.BooleanField(required=False, default=False)
    technical_issue = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        category = attrs['category']
        issue_type = attrs['issue_type']
        allowed = {value for value, _ in constants.issue_type_choices(category)}
        if issue_type not in allowed:
            raise serializers.ValidationError({'issue_type': '问题类型与反馈类别不匹配。'})
        snapshot = attrs.get('original_decision_snapshot') or {}
        if not isinstance(snapshot, dict):
            raise serializers.ValidationError({'original_decision_snapshot': '必须是 JSON 对象。'})
        if len(json.dumps(snapshot, ensure_ascii=False, default=str)) > 20000:
            raise serializers.ValidationError({'original_decision_snapshot': '摘要过大，请只保留必要字段。'})
        for item in attrs.get('evidence') or []:
            if item.get('attachment_id'):
                raise serializers.ValidationError({
                    'evidence': '创建反馈时不能引用附件；请先保存工单，再上传附件并补充证据。',
                })
        return attrs


class EvidenceAddSerializer(serializers.Serializer):
    items = EvidenceInputSerializer(many=True, allow_empty=False)
    reason = serializers.CharField(max_length=4000, required=False, allow_blank=True, default='')

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError('至少提供一条证据。')
        return items


class TeacherActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=sorted(HANDLERS.keys()))
    expected_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=8000, required=False, allow_blank=True, default='')
    owner_id = serializers.IntegerField(required=False, allow_null=True)
    owner_role = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.OWNER_ROLE_CHOICES],
        required=False, allow_blank=True,
    )
    impact_level = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.IMPACT_CHOICES], required=False,
    )
    novelty = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.NOVELTY_CHOICES], required=False,
    )
    conflict_flag = serializers.BooleanField(required=False)
    missing_slots = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, allow_empty=True,
    )
    due_at = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    evidence_refs = serializers.ListField(
        child=serializers.CharField(max_length=255), required=False, allow_empty=True,
    )
    handling_destination = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.DESTINATION_CHOICES],
        required=False, allow_blank=True,
    )
    handling_action = serializers.CharField(max_length=4000, required=False, allow_blank=True, default='')
    handling_note = serializers.CharField(max_length=8000, required=False, allow_blank=True, default='')
    referral_id = serializers.UUIDField(required=False, allow_null=True)
    referral_status = serializers.ChoiceField(
        choices=[constants.REFERRAL_ACKNOWLEDGED, constants.REFERRAL_DECLINED],
        required=False,
    )
    ack_note = serializers.CharField(max_length=4000, required=False, allow_blank=True, default='')
    external_ref = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    destination = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.DESTINATION_CHOICES],
        required=False, allow_blank=True,
    )
    conclusion = serializers.ChoiceField(
        choices=[constants.STATUS_CONFIRMED, constants.STATUS_REJECTED], required=False,
    )
    effect_status = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.EFFECT_CHOICES], required=False,
    )
    effect_note = serializers.CharField(max_length=4000, required=False, allow_blank=True, default='')
    retest_fact_ref = serializers.CharField(max_length=96, required=False, allow_blank=True, default='')
    retest_attempt_ref = serializers.CharField(max_length=128, required=False, allow_blank=True, default='')
    main_ticket_id = serializers.UUIDField(required=False, allow_null=True)
    referral_note = serializers.CharField(max_length=4000, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        action = attrs['action']
        required = {
            'assign': ('owner_id',),
            'request_evidence': ('reason',),
            'confirm': ('reason',),
            'reject': ('reason',),
            'revise_review': ('reason', 'conclusion'),
            'start_handling': ('handling_action',),
            'refer': ('destination', 'reason'),
            'ack_referral': ('referral_id',),
            'reopen': ('reason',),
            'note': ('reason',),
            'set_effect': ('effect_status',),
            'confirm_duplicate': ('main_ticket_id', 'reason'),
            'split_duplicate': ('reason',),
        }.get(action, ())
        missing = [field for field in required if not attrs.get(field)]
        if missing:
            raise serializers.ValidationError({field: '该动作需要此字段。' for field in missing})
        if action == 'triage' and not any(
            field in attrs for field in ('impact_level', 'novelty', 'conflict_flag')
        ):
            raise serializers.ValidationError('至少登记影响、新颖性或证据冲突中的一项。')
        if action == 'ack_referral' and attrs.get('referral_status') == constants.REFERRAL_DECLINED:
            if not attrs.get('ack_note'):
                raise serializers.ValidationError({'ack_note': '退回转交时必须说明原因。'})
        if action == 'set_effect' and attrs.get('effect_status') == constants.EFFECT_VERIFIED:
            if not attrs.get('retest_fact_ref') or not attrs.get('retest_attempt_ref'):
                raise serializers.ValidationError({
                    'retest_fact_ref': '标记已验证必须提供真实复测事实和复测尝试。',
                })
        return attrs


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    visibility = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.VISIBILITY_CHOICES],
        required=False, default=constants.VISIBILITY_STUDENT,
    )

    def validate_file(self, value):
        name = os.path.basename(value.name or '')
        extension = os.path.splitext(name)[1].lower()
        if extension not in constants.ATTACHMENT_ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f'不允许的附件类型：{extension or "无扩展名"}。'
            )
        if value.size > constants.ATTACHMENT_MAX_BYTES:
            raise serializers.ValidationError(
                f'附件超过 {constants.ATTACHMENT_MAX_BYTES // (1024 * 1024)} MB 限制。'
            )
        return value


class SamplingBatchCreateSerializer(serializers.Serializer):
    scope = serializers.JSONField(required=False, default=dict)
    sample_size = serializers.IntegerField(required=False, min_value=1)
    sample_ratio = serializers.FloatField(required=False, min_value=0.0001, max_value=1)
    random_seed = serializers.IntegerField(required=False, min_value=0)
    risk_ticket_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True,
    )
    exclude_prior = serializers.BooleanField(required=False, default=True)
    include_duplicates = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        if attrs.get('sample_size') is None and attrs.get('sample_ratio') is None:
            raise serializers.ValidationError('必须提供 sample_size 或 sample_ratio。')
        return attrs


class Phase3CandidateStubSerializer(serializers.Serializer):
    """Intentionally minimal: phase 3 is not enabled in this build."""

    issue_group_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    baseline_config_version = serializers.CharField(required=False, allow_blank=True)
    candidate_config_version = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        raise serializers.ValidationError(phase3.disabled_response())


class IssueGroupCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    category = serializers.ChoiceField(choices=[c[0] for c in constants.CATEGORY_CHOICES])
    issue_type = serializers.CharField(max_length=48)
    catalog_version = serializers.CharField(max_length=64, required=False, allow_blank=True)
    task_key = serializers.CharField(max_length=80, required=False, allow_blank=True, default='')
    task_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')
    window_start = serializers.DateTimeField()
    window_end = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class IssueGroupMemberSerializer(serializers.Serializer):
    feedback_id = serializers.UUIDField()
    included = serializers.BooleanField(default=True)
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class IssueGroupConfirmSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class IssueGroupRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False)


class IssueGroupSplitSerializer(serializers.Serializer):
    feedback_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')


class IssueGroupMergeSerializer(serializers.Serializer):
    group_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')


class CandidateCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    issue_group_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    baseline_config_version = serializers.CharField(max_length=64)
    candidate_config_version = serializers.CharField(max_length=64)
    single_changed_factor = serializers.CharField(max_length=128)
    target_task_versions = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    excluded_scope = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    expected_risk = serializers.CharField(required=False, allow_blank=True, default='')
    rollback_version = serializers.CharField(max_length=64)
    baseline_config = serializers.DictField(required=False, default=dict)
    candidate_config = serializers.DictField(required=False, default=dict)


class CandidateReportSerializer(serializers.Serializer):
    run_id = serializers.CharField(max_length=128)
    report_id = serializers.CharField(max_length=128)
    report_version = serializers.CharField(max_length=64)
    report_digest = serializers.CharField(max_length=64)
    dataset_version = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    baseline_config_digest = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    candidate_config_digest = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    recommendation = serializers.ChoiceField(
        choices=[c[0] for c in constants.REPORT_RECOMMENDATION_CHOICES],
    )
    completed = serializers.BooleanField(default=False)
    missing_cases = serializers.IntegerField(required=False, default=0)


class CandidateApproveSerializer(serializers.Serializer):
    scope = serializers.CharField(allow_blank=False)
    observation_window = serializers.CharField(allow_blank=False)
    rollback_condition = serializers.CharField(allow_blank=False)


class CandidateActivateSerializer(serializers.Serializer):
    applicable_future_tasks = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class CandidateObserveSerializer(serializers.Serializer):
    report_id = serializers.CharField(max_length=128, required=False, allow_blank=True, default='')
    status = serializers.ChoiceField(
        choices=[c[0] for c in constants.OBSERVATION_STATUS_CHOICES],
        required=False,
    )
    new_failures = serializers.IntegerField(required=False, allow_null=True)
    normal_block_rate = serializers.DictField(required=False, allow_null=True)
    unauthorized_allow_rate = serializers.DictField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default='')


class CandidateRollbackSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False)
    result = serializers.ChoiceField(choices=[c[0] for c in constants.ROLLBACK_RESULT_CHOICES])
