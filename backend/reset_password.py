import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()
admin = User.objects.filter(username='admin').first()
if admin:
    admin.set_password('admin123')
    admin.save()
    print('密码已重置为: admin123')
else:
    print('用户不存在')
