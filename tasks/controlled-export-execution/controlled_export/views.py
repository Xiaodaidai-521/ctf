from pathlib import Path

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authn import IsTrustedService, TrustedServiceAuthentication
from .errors import (
    AuthorizationRejected,
    ContractError,
    ControlledExportError,
    ExecutionConflict,
    IdempotencyConflict,
    ShareAccessDenied,
    UnsupportedContent,
)
from .models import DeliveryAttempt, ShareGrant
from .serializers import (
    CreateShareSerializer,
    DeliveryResultSerializer,
    ExecuteExportSerializer,
    delivery_payload,
    share_payload,
)
from .services import (
    authorize_share_access,
    create_share_grant,
    execute_authorized_export,
    record_delivery_result,
    revoke_share_grant,
    rotate_share_token,
    stream_delivery,
)


def _error_response(exc):
    if isinstance(exc, (IdempotencyConflict, ExecutionConflict)):
        http_status = status.HTTP_409_CONFLICT
    elif isinstance(exc, (AuthorizationRejected, ShareAccessDenied)):
        http_status = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, UnsupportedContent):
        http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        http_status = status.HTTP_400_BAD_REQUEST
    return Response({"error_code": exc.code, "detail": str(exc)}, status=http_status)


def _required_header(request, name, max_length=300):
    value = request.headers.get(name, "").strip()
    if not value or len(value) > max_length:
        raise ContractError(f"{name} header is required", code="HEADER_REQUIRED")
    return value


class InternalView(APIView):
    authentication_classes = [TrustedServiceAuthentication]
    permission_classes = [IsTrustedService]
    parser_classes = [JSONParser]


class ExecuteExportView(InternalView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ExecuteExportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        try:
            receipt, replay = execute_authorized_export(
                authorization=serializer.validated_data["authorization"],
                signature=_required_header(request, "X-Authorization-Signature", 64),
                plan=serializer.validated_data["plan"],
                filename=Path(upload.name).name,
                content=upload.read(),
                idempotency_key=_required_header(request, "Idempotency-Key", 200),
                caller_id=request.user.service_id,
            )
        except ControlledExportError as exc:
            return _error_response(exc)
        receipt["idempotent_replay"] = replay
        return Response(receipt, status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED)


class CreateShareView(InternalView):
    def post(self, request):
        serializer = CreateShareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            share, token, replay = create_share_grant(
                **serializer.validated_data,
                idempotency_key=_required_header(request, "Idempotency-Key", 200),
                caller_id=request.user.service_id,
            )
        except ControlledExportError as exc:
            return _error_response(exc)
        return Response(
            share_payload(share, token=token, replay=replay),
            status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED,
        )


class RotateShareTokenView(InternalView):
    def post(self, request, share_id):
        try:
            share, token = rotate_share_token(share_id=share_id, caller_id=request.user.service_id)
        except ShareGrant.DoesNotExist:
            return Response({"error_code": "SHARE_NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)
        except ControlledExportError as exc:
            return _error_response(exc)
        return Response(share_payload(share, token=token))


class RevokeShareView(InternalView):
    def post(self, request, share_id):
        try:
            share, replay = revoke_share_grant(share_id=share_id, caller_id=request.user.service_id)
        except ShareGrant.DoesNotExist:
            return Response({"error_code": "SHARE_NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)
        return Response(share_payload(share, replay=replay))


class RecordDeliveryResultView(InternalView):
    def post(self, request, delivery_id):
        serializer = DeliveryResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            delivery, replay = record_delivery_result(
                delivery_id=delivery_id,
                status=values["status"],
                bytes_sent=values.get("bytes_sent"),
                evidence_ref=values.get("evidence_ref", ""),
            )
        except DeliveryAttempt.DoesNotExist:
            return Response({"error_code": "DELIVERY_NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)
        except ControlledExportError as exc:
            return _error_response(exc)
        payload = delivery_payload(delivery)
        payload["idempotent_replay"] = replay
        return Response(payload)


class ShareAccessView(APIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, share_id, operation):
        try:
            delivery, artifact = authorize_share_access(
                share_id=share_id,
                recipient_id=request.user.pk,
                token=_required_header(request, "X-Share-Token", 300),
                operation=operation,
            )
        except ShareGrant.DoesNotExist:
            return Response({"error_code": "SHARE_ACCESS_DENIED"}, status=status.HTTP_403_FORBIDDEN)
        except ControlledExportError as exc:
            return _error_response(exc)

        response = StreamingHttpResponse(
            stream_delivery(delivery, artifact),
            content_type={"csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}[
                artifact.output_format
            ],
        )
        disposition = "inline" if operation == "preview" else "attachment"
        response["Content-Disposition"] = (
            f'{disposition}; filename="protected-{artifact.output_asset_version_id}.{artifact.output_format}"'
        )
        response["Cache-Control"] = "no-store, private, max-age=0"
        response["Pragma"] = "no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Delivery-Id"] = str(delivery.delivery_id)
        return response
