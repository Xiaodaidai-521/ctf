"""
ASGI config for ctf_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')

from .security_bootstrap import guard_private_upload_asgi

application = guard_private_upload_asgi(get_asgi_application())
