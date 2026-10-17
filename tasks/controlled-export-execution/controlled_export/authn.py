import hmac
from dataclasses import dataclass

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission


@dataclass(frozen=True)
class ServicePrincipal:
    service_id: str

    @property
    def is_authenticated(self):
        return True

    @property
    def is_staff(self):
        return True

    @property
    def pk(self):
        return self.service_id


class TrustedServiceAuthentication(BaseAuthentication):
    header = "HTTP_X_INTERNAL_AUTHORIZATION"

    def authenticate(self, request):
        configured = settings.CONTROLLED_EXPORT_INTERNAL_KEY
        supplied = request.META.get(self.header, "")
        if not configured:
            raise AuthenticationFailed("Trusted service authentication is not configured")
        if not supplied.startswith("Bearer "):
            raise AuthenticationFailed("Trusted service credential is required")
        candidate = supplied.removeprefix("Bearer ")
        if not hmac.compare_digest(candidate, configured):
            raise AuthenticationFailed("Trusted service credential is invalid")
        service_id = request.META.get("HTTP_X_CALLER_ID", "").strip()
        if not service_id or len(service_id) > 160:
            raise AuthenticationFailed("A bounded X-Caller-Id is required")
        return ServicePrincipal(service_id), None


class IsTrustedService(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, ServicePrincipal)
