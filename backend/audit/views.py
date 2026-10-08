"""Read-only audit APIs and hash-chain verification endpoints."""

from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics

from .models import AIAuditLog, AuditEvent, AuditLedgerEntry
from .serializers import (
    AIAuditLogSerializer,
    AuditEventSerializer,
    AuditLedgerEntrySerializer,
)
from .services import AuditLedgerService


class IsAuditAdmin(BasePermission):
    """Allow only authenticated platform administrators."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or getattr(request.user, 'role', '') == 'admin')
        )


class AuditEventListView(generics.ListAPIView):
    """List platform audit events."""

    serializer_class = AuditEventSerializer
    permission_classes = [IsAuditAdmin]

    def get_queryset(self):
        queryset = AuditEvent.objects.select_related('user').order_by('-created_at')
        category = self.request.query_params.get('category')
        level = self.request.query_params.get('level')
        user_id = self.request.query_params.get('user_id')
        if category:
            queryset = queryset.filter(category=category)
        if level:
            queryset = queryset.filter(level=level)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        return queryset


class AIAuditLogListView(generics.ListAPIView):
    """List AI audit logs without exposing full prompt and response text."""

    serializer_class = AIAuditLogSerializer
    permission_classes = [IsAuditAdmin]

    def get_queryset(self):
        queryset = (
            AIAuditLog.objects
            .select_related('user', 'challenge')
            .order_by('-created_at')
        )
        provider = self.request.query_params.get('provider')
        success = self.request.query_params.get('success')
        user_id = self.request.query_params.get('user_id')
        if provider:
            queryset = queryset.filter(provider=provider)
        if success is not None:
            queryset = queryset.filter(success=success.lower() == 'true')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        return queryset


class AuditLedgerEntryListView(generics.ListAPIView):
    """List hash-chain audit ledger entries."""

    serializer_class = AuditLedgerEntrySerializer
    permission_classes = [IsAuditAdmin]

    def get_queryset(self):
        queryset = AuditLedgerEntry.objects.select_related('actor').order_by('-id')
        event_category = self.request.query_params.get('event_category')
        object_type = self.request.query_params.get('object_type')
        object_id = self.request.query_params.get('object_id')
        if event_category:
            queryset = queryset.filter(event_category=event_category)
        if object_type:
            queryset = queryset.filter(object_type=object_type)
        if object_id:
            queryset = queryset.filter(object_id=object_id)
        return queryset


class AuditLedgerVerifyView(APIView):
    """Verify the complete hash-chain ledger."""

    permission_classes = [IsAuditAdmin]

    def get(self, request):
        return self._verify()

    def post(self, request):
        return self._verify()

    def _verify(self):
        result = AuditLedgerService.verify_chain()
        return Response(
            {
                'is_valid': result.is_valid,
                'checked_count': result.checked_count,
                'total_entries': result.checked_count,
                'errors': [
                    {
                        'entry_id': error.entry_id,
                        'field': error.field,
                        'expected': error.expected,
                        'actual': error.actual,
                    }
                    for error in result.errors
                ],
            },
            status=status.HTTP_200_OK,
        )
