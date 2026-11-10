import os

from django.core.asgi import get_asgi_application
from controlled_export_service.security_bootstrap import guard_private_upload_asgi


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "controlled_export_service.settings")
application = guard_private_upload_asgi(get_asgi_application())
