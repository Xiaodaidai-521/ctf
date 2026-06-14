#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

# 加载项目根目录 .env（确定性路径，不依赖 CWD）
try:
    from dotenv import load_dotenv
    _root_dotenv = Path(__file__).resolve().parent.parent / '.env'
    if _root_dotenv.exists():
        load_dotenv(_root_dotenv)
except ImportError:
    pass


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
