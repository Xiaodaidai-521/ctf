"""Private-file HTTP capabilities supplied only by the explicit composition root."""
from uuid import UUID

from django.http import HttpResponse
from django.urls import path
from django.utils.http import content_disposition_header
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from data_security.contracts import ProtectionError, ReasonCode


_owners = None
_shares = None


def bind_private_files(owners=None, shares=None):
    global _owners, _shares
    _owners, _shares = owners, shares


def private_files(domain):
    if _owners is None:
        return None
    return _owners.get(domain) or ProtectionError(schema_version=ProtectionError.SCHEMA,
        code=ReasonCode.SOURCE_NOT_APPROVED, retryable=False, trace_id='private-files/closed')


def upload_operation_id(request):
    """The transport id names a retry, never the server's encryption object UUID."""
    raw = request.headers.get('X-File-Operation-ID', '')
    try:
        operation_id = UUID(raw)
    except (ValueError, AttributeError):
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.INVALID_VALUE,
            retryable=False, trace_id='private-files/operation-id')
    if raw != str(operation_id):
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.INVALID_VALUE,
            retryable=False, trace_id='private-files/operation-id')
    return operation_id


def private_file_error(error):
    code = error.code if isinstance(error, ProtectionError) else ReasonCode.SOURCE_NOT_APPROVED
    status = 409
    if code in (ReasonCode.AUTHORIZATION_DENIED, ReasonCode.AUTHORIZATION_EXPIRED):
        status = 403
    elif code is ReasonCode.SOURCE_NOT_APPROVED:
        status = 503
    elif code in (ReasonCode.INVALID_VALUE, ReasonCode.LIMIT_EXCEEDED):
        status = 400
    return Response({'code': code.value, 'detail': '文件暂时无法处理，请稍后重试。'},
        status=status, headers={'Cache-Control': 'no-store'})


def private_file_response(payload, *, filename):
    # Only an already fully authenticated in-memory payload reaches this boundary.
    response = HttpResponse(payload.binary, content_type='application/octet-stream', headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Content-Disposition': content_disposition_header(True, filename),
    })
    return response


def operation_response(operation, operation_id):
    # Do not serialize the server-only intention, paths, crypto context or stored references.
    return Response({'operation_id': str(operation_id), 'state': operation.state,
        'result_id': operation.result_ref, 'network_delivery_confirmed': False},
        headers={'Cache-Control': 'no-store'})


def create_private_share(request, *, domain, object_id, ticket_id=None, field='file'):
    if _shares is None:
        return private_file_error(None)
    operation_id = upload_operation_id(request)
    if isinstance(operation_id, ProtectionError):
        return private_file_error(operation_id)
    result = _shares.create(user=request.user, operation_id=operation_id,
        domain=domain, object_id=object_id, ticket_id=ticket_id, field=field)
    if isinstance(result, ProtectionError):
        return private_file_error(result)
    value = result.to_value()
    return Response({**value, 'operation_id': str(operation_id),
        'download_url': f"/api/data-security/files/shares/{value['share_id']}/"},
        status=201, headers={'Cache-Control': 'no-store'})


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def private_share(request, share_id):
    if _shares is None:
        return private_file_error(None)
    if request.method == 'DELETE':
        result = _shares.revoke(user=request.user, share_id=share_id)
        if isinstance(result, ProtectionError):
            return private_file_error(result)
        return Response(status=204, headers={'Cache-Control': 'no-store'})
    payload = _shares.open(user=request.user, share_id=share_id)
    if isinstance(payload, ProtectionError):
        return private_file_error(payload)
    return private_file_response(payload, filename='attachment.bin')


urlpatterns = [path('files/shares/<uuid:share_id>/', private_share, name='private-file-share')]
