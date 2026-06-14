import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')

import django
django.setup()

from users.models import CTFUser
from django.contrib.auth import authenticate

# 重置 admin 密码
admin = CTFUser.objects.get(username='admin')
admin.set_password('admin123456')
admin.role = 'admin'
admin.save()

# 验证
user = authenticate(username='admin', password='admin123456')
print(f'authenticate result: {user}')
print(f'username: {user.username}, role: {user.role}')
print('Password reset OK!')
