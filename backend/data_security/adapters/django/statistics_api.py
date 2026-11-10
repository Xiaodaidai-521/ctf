"""Admin-only metadata mapping; statistics are supplied by explicit assembly."""
from typing import Callable

from django.urls import path
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from data_security.contracts import ContractViolation, FrozenJSON, ProtectionError, ReasonCode
from data_security.contracts.schema import count, require

_reader: Callable[[int], FrozenJSON | ProtectionError] | None = None


def bind_statistics_api(reader=None):
    global _reader
    _reader = reader


class StatisticsView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = ()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store, private'
        response['Pragma'] = 'no-cache'
        return response

    def get(self, request):
        if not request.user.is_active or request.user.role != 'admin':
            return Response({'code': 'AUTHORIZATION_DENIED'}, status=403)
        if _reader is None:
            return Response({'code': 'POLICY_NOT_APPROVED', 'state': 'disabled'}, status=503)
        try:
            require(not set(request.query_params) - {'offset'}, ReasonCode.UNKNOWN_FIELD)
            require(len(request.query_params.getlist('offset')) <= 1)
            offset = int(request.query_params.get('offset', '0'))
            count(offset)
        except ContractViolation as error:
            return Response({'code': error.code.value}, status=400)
        except ValueError:
            return Response({'code': 'INVALID_TYPE'}, status=400)
        result = _reader(offset)
        if isinstance(result, ProtectionError):
            return Response({'code': result.code.value, 'state': 'unknown'}, status=503)
        return Response(result.to_value())


urlpatterns = [path('stats/', StatisticsView.as_view(), name='security-statistics')]
