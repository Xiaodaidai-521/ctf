import json

from django.conf import settings
from rest_framework import serializers


def _json_object(value, field):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise serializers.ValidationError(f"{field} must contain valid JSON") from exc
    if not isinstance(value, dict):
        raise serializers.ValidationError(f"{field} must be an object")
    return value


class ExecuteExportSerializer(serializers.Serializer):
    authorization = serializers.JSONField()
    plan = serializers.JSONField()
    file = serializers.FileField()

    def validate_authorization(self, value):
        return _json_object(value, "authorization")

    def validate_plan(self, value):
        return _json_object(value, "plan")

    def validate_file(self, value):
        if value.size <= 0:
            raise serializers.ValidationError("Input file is empty")
        if value.size > settings.CONTROLLED_EXPORT_MAX_INPUT_BYTES:
            raise serializers.ValidationError("Input file exceeds the configured size limit")
        return value


class CreateShareSerializer(serializers.Serializer):
    execution_id = serializers.UUIDField()
    recipient_id = serializers.CharField(max_length=160, trim_whitespace=True)
    allowed_operations = serializers.ListField(
        child=serializers.ChoiceField(choices=["preview", "download"]),
        allow_empty=False,
    )
    expires_at = serializers.DateTimeField()


class DeliveryResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["completed", "failed", "unknown"])
    bytes_sent = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    evidence_ref = serializers.CharField(max_length=300, allow_blank=True, required=False)


def share_payload(share, *, token=None, replay=False):
    return {
        "share_id": str(share.share_id),
        "execution_id": str(share.execution_id),
        "output_asset_version_id": str(share.artifact_id),
        "recipient_id": share.recipient_id,
        "allowed_operations": share.allowed_operations,
        "expires_at": share.expires_at.isoformat(),
        "revoked_at": share.revoked_at.isoformat() if share.revoked_at else None,
        "grant_version": share.grant_version,
        "token": token,
        "idempotent_replay": replay,
        "token_recovery": "rotate_required" if replay and token is None else None,
    }


def delivery_payload(delivery):
    return {
        "delivery_id": str(delivery.delivery_id),
        "share_id": str(delivery.share_id),
        "execution_id": str(delivery.execution_id),
        "recipient_id": delivery.recipient_id,
        "operation": delivery.operation,
        "status": delivery.status,
        "actual_content_hash": delivery.actual_content_hash,
        "bytes_sent": delivery.bytes_sent,
        "delivered_record_count": delivery.delivered_record_count,
        "measurement_basis": delivery.measurement_basis,
        "admitted_at": delivery.admitted_at.isoformat(),
        "response_started_at": delivery.response_started_at.isoformat() if delivery.response_started_at else None,
        "completed_at": delivery.completed_at.isoformat() if delivery.completed_at else None,
        "error_code": delivery.error_code or None,
    }
