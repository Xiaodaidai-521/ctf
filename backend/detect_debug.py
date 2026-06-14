import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()
from ai_assistant.challenge_detector import detect_challenge

for msg in ['SQL注入入门怎么做', 'SQL注入', '注入', '入口']:
    result, method = detect_challenge(msg, None)
    title = result['title'] if result else None
    print(f'msg={msg!r} -> title={title}, method={method}')
