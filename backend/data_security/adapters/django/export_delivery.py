"""Reference-only HTTP delivery; the owner re-fetches every source and approval."""
from django.urls import path
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


urlpatterns = [path('exports/resources/<str:operation>/', resource_export, name='resource-export')]
