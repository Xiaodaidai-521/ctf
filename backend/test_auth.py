import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')

import django
django.setup()

from django.contrib.auth import authenticate
from users.models import CTFUser

# 测试认证
user = authenticate(username='admin', password='admin123456')
print(f'authenticate result: {user}')
if user:
    print(f'user: {user.username}, role: {user.role}')
else:
    print('auth failed!')

# 检查密码
admin = CTFUser.objects.get(username='admin')
pwd_ok = admin.check_password('admin123456')
print(f'check_password: {pwd_ok}')

# 列出所有用户
print('\nAll users:')
for u in CTFUser.objects.all():
    print(f'  username={u.username}, role={u.role}, is_active={u.is_active}')
