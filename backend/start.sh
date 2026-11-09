#!/bin/bash
# CTF Platform 后端启动脚本（生产环境）

set -e

echo "=== CTF Platform Backend Starting ==="

# B is the only startup source for a configured database URL.
until python - <<'PY' 2>/dev/null
import psycopg2
from ctf_backend.security_bootstrap import startup_database_url
url = startup_database_url()
if url:
    psycopg2.connect(url).close()
PY
do
    echo "DATABASE_NOT_READY"
    sleep 2
done

# 执行数据库迁移
echo "Running database migrations..."
python manage.py migrate --noinput

# 收集静态文件
echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || true

# No environment-password interpolation or unattended administrator creation.
# Use the validated user-management entry after explicit authorization.
echo "=== Starting Gunicorn ==="
exec gunicorn \
    --bind 127.0.0.1:8000 \
    --workers ${GUNICORN_WORKERS:-4} \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - \
    --access-logformat '%(s)s %(D)s' \
    --error-logfile - \
    --log-level info \
    ctf_backend.wsgi:application
