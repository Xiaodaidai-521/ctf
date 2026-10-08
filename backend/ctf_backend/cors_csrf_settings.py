# Django Settings for CSRF and CORS
# 支持通过 ALLOWED_ORIGINS 环境变量配置生产域名

import os

# Environment-aware debug flag, kept in sync with settings.py behavior.
_db_url = os.environ.get('DATABASE_URL', '')
_env_debug = os.environ.get('DEBUG', '').lower()
if _env_debug:
    _debug = _env_debug in ('true', '1', 'yes')
else:
    _debug = not bool(_db_url)

_allowed_origins = [
    origin.strip()
    for origin in os.environ.get('ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
]

# CORS settings
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = _allowed_origins
CORS_ALLOW_CREDENTIALS = True

# CSRF settings
# 基础开发域名
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8080',
    'http://127.0.0.1:8080',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost',
    'http://127.0.0.1',
]

# 生产环境：从 ALLOWED_ORIGINS 环境变量追加域名
# 格式：https://ctf.example.com,https://www.ctf.example.com
for origin in _allowed_origins:
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Session settings for development
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_HTTPONLY = True

