"""Serializers for audit APIs."""

from rest_framework import serializers

from .models import AIAuditLog, AuditEvent, AuditLedgerEntry


class AuditUserSerializer(serializers.Serializer):
    """Compact user payload for audit records."""

    id = serializers.IntegerField()
    username = serializers.CharField()
    nickname = serializers.CharField(allow_blank=True)


class AuditEventSerializer(serializers.ModelSerializer):
    """Serializer for generic audit events."""

    user = AuditUserSerializer(read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            'id',
            'category',
            'level',
            'summary',
            'detail',
            'ip_address',
            'user_agent',
            'user',
            'username',
            'created_at',
        ]
        read_only_fields = fields


class AIAuditLogSerializer(serializers.ModelSerializer):
    """Serializer for AI audit logs."""

    user = AuditUserSerializer(read_only=True)
    challenge_title = serializers.CharField(source='challenge.title', read_only=True)

    class Meta:
        model = AIAuditLog
        fields = [
            'id',
            'provider',
            'model',
            'mode',
            'success',
            'error_message',
            'duration_ms',
            'token_estimate',
            'ip_address',
            'user',
            'challenge',
            'challenge_title',
            'created_at',
        ]
        read_only_fields = fields


class AuditLedgerEntrySerializer(serializers.ModelSerializer):
    """Serializer for hash-chain ledger entries."""

    actor = AuditUserSerializer(read_only=True)

    class Meta:
        model = AuditLedgerEntry
        fields = [
            'id',
            'event_category',
            'object_type',
            'object_id',
            'actor',
            'payload',
            'payload_hash',
            'previous_hash',
            'current_hash',
            'chain_version',
            'created_at',
        ]
        read_only_fields = fields
