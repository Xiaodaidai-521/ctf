#!/bin/bash
# CTF Platform 后端启动脚本（生产环境）

set -e

echo "=== CTF Platform Backend Starting ==="

# 等待 PostgreSQL 就绪（如果使用 PostgreSQL）
if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -q "postgres"; then
    echo "Waiting for PostgreSQL..."
    until python -c "
import psycopg2
import os
import time
url = os.environ.get('DATABASE_URL', '')
# 解析 DATABASE_URL: postgres://user:pass@host:port/dbname
import re
m = re.match(r'postgres(?:ql)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', url)
if m:
    conn = psycopg2.connect(host=m.group(3), port=m.group(4), user=m.group(1), password=m.group(2), dbname=m.group(5))
    conn.close()
    print('PostgreSQL is ready')
else:
    print('Invalid DATABASE_URL format')
    exit(1)
" 2>/dev/null; do
        echo "PostgreSQL not ready, retrying in 2s..."
        sleep 2
    done
fi

# 执行数据库迁移
echo "Running database migrations..."
python manage.py migrate --noinput

# 收集静态文件
echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || true

# 创建超级管理员（如果设置了环境变量且用户不存在）
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')
    print('Superuser created successfully')
else:
    print('Superuser already exists')
"
fi

echo "=== Starting Gunicorn ==="
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers ${GUNICORN_WORKERS:-4} \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    ctf_backend.wsgi:application
