from rest_framework import serializers

from . import constants


class SubmissionCreateSerializer(serializers.Serializer):
    client_submission_id = serializers.CharField(max_length=96)
    payload = serializers.DictField()
    assistance_tracking = serializers.ChoiceField(
        choices=[choice[0] for choice in constants.ASSISTANCE_TRACKING_CHOICES],
        required=False,
        default=constants.ASSISTANCE_TRACKING_COMPLETE,
    )


class HintRequestSerializer(serializers.Serializer):
    level = serializers.IntegerField(min_value=1, max_value=4)
    source = serializers.ChoiceField(
        choices=[constants.ASSISTANCE_SOURCE_AI, constants.ASSISTANCE_SOURCE_CARD],
    )
    content_ref = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')


class AnalysisViewSerializer(serializers.Serializer):
    content_ref = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')


class TeacherHelpSerializer(serializers.Serializer):
    summary = serializers.CharField(max_length=500)


class ManualReviewSerializer(serializers.Serializer):
    scores = serializers.DictField()
    decision = serializers.ChoiceField(choices=['pass', 'fail'])
    remarks = serializers.CharField(allow_blank=False)
    causes = serializers.ListField(
        child=serializers.ChoiceField(choices=[choice[0] for choice in constants.ERROR_CAUSE_CHOICES]),
        required=False,
        default=list,
    )


class ErrorCauseSerializer(serializers.Serializer):
    cause = serializers.ChoiceField(choices=[choice[0] for choice in constants.ERROR_CAUSE_CHOICES])
    status = serializers.ChoiceField(choices=[choice[0] for choice in constants.CAUSE_STATUS_CHOICES])
    note = serializers.CharField(required=False, allow_blank=True, default='')


class ReviewCardSerializer(serializers.Serializer):
    original_task_summary = serializers.CharField(required=False, allow_blank=True)
    error_evidence = serializers.CharField(required=False, allow_blank=True)
    judgment_at_time = serializers.CharField(required=False, allow_blank=True)
    correct_basis = serializers.CharField(required=False, allow_blank=True)
    next_verification = serializers.CharField(required=False, allow_blank=True)
    student_reflection = serializers.CharField(required=False, allow_blank=True)
    complete = serializers.BooleanField(required=False, default=False)


class CardConfirmSerializer(serializers.Serializer):
    confirmation = serializers.CharField(allow_blank=False)


class RetestScheduleSerializer(serializers.Serializer):
    due_days = serializers.IntegerField(required=False, min_value=0, max_value=60)
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class DisputeCreateSerializer(serializers.Serializer):
    client_dispute_id = serializers.CharField(max_length=96)
    reason = serializers.CharField(allow_blank=False)


class DisputeResolveSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[constants.DISPUTE_RESOLVED, constants.DISPUTE_REJECTED],
    )
    resolution = serializers.CharField(allow_blank=False)


class SamplingBatchSerializer(serializers.Serializer):
    catalog_version = serializers.CharField(max_length=64)
    title = serializers.CharField(max_length=200)
    window_start = serializers.DateTimeField()
    window_end = serializers.DateTimeField()
    basis = serializers.CharField(allow_blank=False)
    deadline = serializers.DateTimeField()
    sample_size = serializers.IntegerField(required=False, min_value=0, default=0)
    high_risk_size = serializers.IntegerField(required=False, min_value=0, default=0)
    random_seed = serializers.IntegerField(required=False, default=0)
    task_key = serializers.CharField(max_length=80, required=False, allow_blank=True, default='')
    task_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')
    capability_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')


class SamplingReviewSerializer(serializers.Serializer):
    findings = serializers.DictField()
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    needs_correction = serializers.BooleanField(required=False, default=False)
    correction = serializers.DictField(required=False, allow_null=True)


class CorrectionSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=[choice[0] for choice in constants.CORRECTION_SOURCE_CHOICES])
    reason = serializers.CharField(allow_blank=False)
    changes = serializers.DictField()
    sampling_item_id = serializers.UUIDField(required=False, allow_null=True)


class ProcessDueSerializer(serializers.Serializer):
    now = serializers.DateTimeField(required=False, allow_null=True)
