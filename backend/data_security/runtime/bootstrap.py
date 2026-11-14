"""Bind real field storage without changing login, provider or export permissions."""
from django.conf import settings


def start_runtime_protection():
    if not settings.DATA_PROTECTION_ENABLED:
        return
    from data_security.adapters.persistence.fields import bind_field_storage
    from data_security.runtime.fields import RuntimeFieldStorage
    bind_field_storage(RuntimeFieldStorage())
