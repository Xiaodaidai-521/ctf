"""Formal authentication policy: session login only, legacy tokens disabled.

B explicitly installs this on both DRF defaults and the challenge proxy, whose
legacy decorator otherwise overrides those defaults. No token model is read or
migrated here. Unknown production callers/rows still require separate approval.
"""
from collections.abc import Callable

from django.core.management.base import CommandError
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


_bootstrap_loader: Callable[[], dict] | None = None


def bind_bootstrap_teacher_inputs(loader: Callable[[], dict] | None):
    """B supplies the loader; only M5/approved startup may read secret material."""
    global _bootstrap_loader
    _bootstrap_loader = loader


def bootstrap_teacher_inputs() -> dict:
    if _bootstrap_loader is None:
        raise CommandError('TEACHER_BOOTSTRAP_NOT_BOUND')
    return _bootstrap_loader()


class DisabledTokenAuthentication(BaseAuthentication):
    """Reject old bearer tokens without looking up or retaining their plaintext."""

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if header and header[0].lower() == b'token':
            raise AuthenticationFailed('TOKEN_AUTHENTICATION_DISABLED')
        return None

    def authenticate_header(self, request):
        return 'Token'
