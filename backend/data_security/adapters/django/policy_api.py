"""Read-only policy metadata and server-generated synthetic previews."""
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from data_security.contracts import ProtectionError

_binding = None


def bind_policy_api(*, catalog=None, binding=None, preview=None, key_metadata=(), reveal_state='disabled'):
    global _binding
    _binding = (catalog, binding, preview, key_metadata, reveal_state) if catalog is not None else None


def _access(request):
    if not request.user.is_active or request.user.role != 'admin':
        return Response({'code': 'AUTHORIZATION_DENIED'}, status=403)
    if _binding is None:
        return Response({'code': 'POLICY_NOT_APPROVED'}, status=503)
    return None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def policies(request):
    denied = _access(request)
    if denied is not None:
        return denied
    catalog, binding, preview, key_metadata, reveal_state = _binding
    snapshot = catalog.snapshot(binding)
    if type(snapshot) is ProtectionError:
        return Response({'code': snapshot.code.value}, status=503)
    return Response({'policy': snapshot.to_wire(), 'keys': key_metadata,
                     'reveal_enabled': reveal_state != 'disabled', 'reveal_state': reveal_state,
                     'preview_source': 'server-synthetic-only'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def preview(request):
    denied = _access(request)
    if denied is not None:
        return denied
    if type(request.data) is not dict or set(request.data) != {'case'} or request.data['case'] not in (
            'email', 'ipv4', 'card', 'mixed'):
        return Response({'code': 'INVALID_VALUE'}, status=400)
    result = _binding[2](request.data['case'], request.user.pk)
    if type(result) is ProtectionError:
        return Response({'code': result.code.value}, status=503)
    response = Response(result)
    response['Cache-Control'] = 'no-store'
    return response


urlpatterns = [path('policies/', policies, name='security-policies'),
               path('preview/', preview, name='security-preview')]
