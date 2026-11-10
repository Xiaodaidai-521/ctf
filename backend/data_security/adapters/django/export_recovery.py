"""Reference-only recovery HTTP boundary; the injected flow determines every effect."""
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from data_security.contracts import ContractViolation, DeliveryReceipt, ProtectionError, ReasonCode
from data_security.contracts.schema import reference, require

_recover = None


def bind_export_recovery(recover=None):
    global _recover
    _recover = recover


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def recover_export(request, operation):
    if _recover is None:
        return Response({'code': 'SOURCE_NOT_APPROVED'}, status=503)
    try:
        require(operation in ('release', 'reconcile'), ReasonCode.INVALID_VALUE)
        require(type(request.data) is dict and set(request.data) == {'execution_ref', 'permission_ref'},
                ReasonCode.INVALID_VALUE)
        for value in request.data.values():
            reference(value, maximum=160)
    except ContractViolation as error:
        return Response({'code': error.code.value}, status=400)
    result = _recover(user=request.user, operation=operation, **request.data)
    if isinstance(result, ProtectionError):
        status = 403 if result.code in (ReasonCode.AUTHORIZATION_DENIED, ReasonCode.AUTHORIZATION_EXPIRED) else 409
        response = Response({'code': result.code.value}, status=status)
    else:
        delivered = isinstance(result, DeliveryReceipt)
        response = Response({'execution_ref': request.data['execution_ref'],
            'state': 'logically_delivered' if delivered else result.state.value,
            'delivered_records': result.delivered_records if delivered else result.settled_amount,
            'network_delivery_confirmed': False})
    response['Cache-Control'] = 'no-store'
    return response


urlpatterns = [path('exports/recovery/<str:operation>/', recover_export, name='export-recovery')]
