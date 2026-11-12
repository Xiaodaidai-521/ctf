"""Reference-only HTTP delivery; the owner re-fetches every source and approval."""
from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from data_security.contracts import ContractViolation, MediaType, ProtectionError, ReasonCode
from data_security.contracts.schema import reference, require
from data_security.adapters.django.private_files import private_file_error, private_file_response


_entry = None


def bind_export_delivery(entry):
    global _entry
    _entry = entry


def export_delivery():
    if _entry is None:
        return ProtectionError(schema_version=ProtectionError.SCHEMA,
            code=ReasonCode.SOURCE_NOT_APPROVED, retryable=False, trace_id='export-delivery/closed')
    return _entry


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resource_export(request, operation):
    owner = export_delivery()
    if isinstance(owner, ProtectionError):
        return private_file_error(owner)
    try:
        require(operation in ('execute', 'download'), ReasonCode.INVALID_VALUE)
        require(type(request.data) is dict and set(request.data) == {'source_ref', 'permission_ref'},
                ReasonCode.INVALID_VALUE)
        for value in request.data.values():
            reference(value, maximum=160)
    except ContractViolation as error:
        return Response({'code': error.code.value, 'detail': '请求内容不正确。'}, status=400,
            headers={'Cache-Control': 'no-store'})
    if operation == 'execute':
        result = owner.execute(user=request.user, **request.data)
        if isinstance(result, ProtectionError):
            return private_file_error(result)
        return Response({'execution_ref': result.binding.execution_id, 'state': 'logically_delivered',
            'delivered_records': result.delivered_records, 'network_delivery_confirmed': False},
            headers={'Cache-Control': 'no-store'})
    payload = owner.open_delivery(user=request.user, **request.data)
    if isinstance(payload, ProtectionError):
        return private_file_error(payload)
    extension = 'csv' if payload.media_type is MediaType.CSV else 'xlsx'
    return private_file_response(payload, filename='export.' + extension)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_records(request):
    """Only current subject grants; a role never expands this list."""
    owner = export_delivery()
    if isinstance(owner, ProtectionError):
        return private_file_error(owner)
    try:
        require(not set(request.query_params) - {'offset', 'resource_id'}, ReasonCode.INVALID_VALUE)
        require(all(len(request.query_params.getlist(key)) == 1 for key in request.query_params), ReasonCode.INVALID_VALUE)
        offset = int(request.query_params.get('offset', '0'))
        require(0 <= offset <= 100000, ReasonCode.INVALID_VALUE)
        resource_id = request.query_params.get('resource_id')
        if resource_id is not None:
            resource_id = int(resource_id)
            require(resource_id > 0, ReasonCode.INVALID_VALUE)
    except (ContractViolation, ValueError):
        return Response({'code': 'INVALID_VALUE'}, status=400)
    from resources.models import ExportSourcePermission
    permissions = ExportSourcePermission.objects.filter(actor_ref='user/' + str(request.user.pk),
        revoked_at__isnull=True, expires_at__gt=timezone.now(), source__revoked_at__isnull=True,
        source__expires_at__gt=timezone.now()).select_related('source__resource').order_by('-pk')
    if resource_id is not None:
        permissions = permissions.filter(source__resource_id=resource_id)
    rows = list(permissions[offset:offset + 21])
    items = []
    for permission in rows[:20]:
        source = permission.source
        # Reuse source ACL, owner metadata and authenticated grants before returning a title.
        loaded = owner.sources.load(user=request.user, source_ref=source.source_ref,
                                    permission_ref=permission.authorization_ref)
        if isinstance(loaded, ProtectionError):
            continue
        description = owner.describe(user=request.user, source_ref=source.source_ref,
                                     permission_ref=permission.authorization_ref)
        if isinstance(description, ProtectionError):
            description = {'state': 'pending', 'can_execute': False, 'can_download': False,
                'protection': {'redaction': 'unknown', 'storage': 'unknown'},
                'expires_at': min(source.expires_at, permission.expires_at).isoformat()}
        items.append({'id': permission.pk, 'resource_id': source.resource_id,
            'title': source.resource.title, 'source_ref': source.source_ref,
            'permission_ref': permission.authorization_ref, **description})
    return Response({'items': items, 'next_offset': offset + 20 if len(rows) > 20 else None},
                    headers={'Cache-Control': 'no-store, private'})


urlpatterns = [path('exports/records/', export_records, name='export-records'),
               path('exports/resources/<str:operation>/', resource_export, name='resource-export')]
