"""
WSGI config for ctf_backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os
from pathlib import Path

from django.core.wsgi import get_wsgi_application

# 加载项目根目录 .env（gunicorn 启动时不经过 manage.py，必须在这里加载）
_root_dotenv = Path(__file__).resolve().parent.parent.parent / '.env'
if _root_dotenv.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_root_dotenv)
    except ImportError:
        pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')

application = get_wsgi_application()
