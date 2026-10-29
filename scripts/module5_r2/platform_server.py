"""Local HTTP platform on a dedicated evidence database; no deployment gates opened."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'backend'))
os.environ['DATABASE_BACKEND'] = 'sqlite'
os.environ['SQLITE_DATABASE_PATH'] = sys.argv[1]
os.environ['DJANGO_SETTINGS_MODULE'] = 'ctf_backend.settings'
import django

django.setup()
from django.conf import settings
from django.core.management import call_command

settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
for name in ('LEARNING_MAP_AI_ENABLED', 'KNOWLEDGE_RAG_SEMANTIC_ENABLED',
             'AGENT_RUNTIME_SEMANTIC_RETRIEVAL', 'TUTOR_AGENT_ROUTER_ENABLED',
             'TUTOR_SPECIALISTS_ENABLED', 'TUTOR_CONTEXT_ENABLED', 'PRACTICAL_TRAINING_ENABLED'):
    setattr(settings, name, False)
call_command('runserver', '127.0.0.1:18380', use_reloader=False, use_threading=False)
