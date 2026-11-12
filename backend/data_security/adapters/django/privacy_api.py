"""User-facing capabilities and own conversation status, separate from admin APIs."""
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from data_security.adapters.persistence.fields import field_storage_enabled
from data_security.adapters.django.private_files import private_files
from data_security.adapters.django.export_delivery import export_delivery
from data_security.adapters.django.protection_status import conversation_protection
from data_security.contracts import ProtectionError


class PrivateResponseMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store, private'
        return response


class PrivacyCapabilitiesView(PrivateResponseMixin, APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        owner = private_files('resources')
        return Response({'field_storage': 'enabled-unverified' if field_storage_enabled() else 'disabled',
            'private_files': 'enabled-unverified' if owner is not None and not isinstance(owner, ProtectionError) else 'disabled',
            'controlled_export': 'enabled-unverified' if not isinstance(export_delivery(), ProtectionError) else 'disabled'})


class ConversationProtectionView(PrivateResponseMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, pk):
        from ai_assistant.models import AIConversation
        conversation = get_object_or_404(AIConversation, pk=pk, user=request.user)
        return Response({'id': conversation.pk, 'protection': conversation_protection(conversation)})


urlpatterns = [path('privacy/capabilities/', PrivacyCapabilitiesView.as_view()),
               path('privacy/conversations/<int:pk>/', ConversationProtectionView.as_view())]
