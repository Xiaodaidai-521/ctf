import os
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent.parent
VAR_DIR = BASE_DIR / "var"
VAR_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.environ.get("CONTROLLED_EXPORT_DJANGO_SECRET", "isolated-development-only")
DEBUG = os.environ.get("CONTROLLED_EXPORT_DEBUG", "false").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [
    value.strip()
    for value in os.environ.get("CONTROLLED_EXPORT_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if value.strip()
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "rest_framework.authtoken",
    "controlled_export",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "controlled_export_service.urls"
WSGI_APPLICATION = "controlled_export_service.wsgi.application"
TEMPLATES = []

DATABASE_URL = os.environ.get("CONTROLLED_EXPORT_DATABASE_URL", "")
if DATABASE_URL.startswith(("postgres://", "postgresql://")):
    parsed = urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username,
            "PASSWORD": parsed.password,
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
            "OPTIONS": {"connect_timeout": 5},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get(
                "CONTROLLED_EXPORT_SQLITE_PATH",
                str(VAR_DIR / "controlled_export.sqlite3"),
            ),
        }
    }

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/hour", "user": "300/hour"},
}

CONTROLLED_EXPORT_ENVIRONMENT = os.environ.get("CONTROLLED_EXPORT_ENVIRONMENT", "evaluation")
if CONTROLLED_EXPORT_ENVIRONMENT not in {"evaluation", "production"}:
    raise RuntimeError("CONTROLLED_EXPORT_ENVIRONMENT must be evaluation or production")
CONTROLLED_EXPORT_PRIVATE_ROOT = Path(
    os.environ.get("CONTROLLED_EXPORT_PRIVATE_ROOT", str(VAR_DIR / "private"))
)
CONTROLLED_EXPORT_PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
CONTROLLED_EXPORT_INTERNAL_KEY = os.environ.get("CONTROLLED_EXPORT_INTERNAL_KEY", "")
EXECUTION_AUTHORITY_HMAC_SECRET = os.environ.get("EXECUTION_AUTHORITY_HMAC_SECRET", "")
SHARE_TOKEN_PEPPER = os.environ.get("SHARE_TOKEN_PEPPER", "")
CONTROLLED_EXPORT_MAX_INPUT_BYTES = int(os.environ.get("CONTROLLED_EXPORT_MAX_INPUT_BYTES", str(20 * 1024 * 1024)))
CONTROLLED_EXPORT_MAX_ROWS = int(os.environ.get("CONTROLLED_EXPORT_MAX_ROWS", "100000"))
CONTROLLED_EXPORT_MAX_COLUMNS = int(os.environ.get("CONTROLLED_EXPORT_MAX_COLUMNS", "512"))
CONTROLLED_EXPORT_MAX_SHARE_SECONDS = int(os.environ.get("CONTROLLED_EXPORT_MAX_SHARE_SECONDS", "86400"))
CONTROLLED_EXPORT_LEASE_SECONDS = int(os.environ.get("CONTROLLED_EXPORT_LEASE_SECONDS", "300"))

if CONTROLLED_EXPORT_ENVIRONMENT == "production":
    required = {
        "CONTROLLED_EXPORT_DJANGO_SECRET": SECRET_KEY != "isolated-development-only",
        "CONTROLLED_EXPORT_INTERNAL_KEY": bool(CONTROLLED_EXPORT_INTERNAL_KEY),
        "EXECUTION_AUTHORITY_HMAC_SECRET": bool(EXECUTION_AUTHORITY_HMAC_SECRET),
        "SHARE_TOKEN_PEPPER": bool(SHARE_TOKEN_PEPPER),
        "CONTROLLED_EXPORT_DATABASE_URL": DATABASE_URL.startswith(("postgres://", "postgresql://")),
        "CONTROLLED_EXPORT_PRIVATE_ROOT": bool(os.environ.get("CONTROLLED_EXPORT_PRIVATE_ROOT")),
        "CONTROLLED_EXPORT_DEBUG=false": not DEBUG,
    }
    missing = [name for name, configured in required.items() if not configured]
    if missing:
        raise RuntimeError(f"Refusing to start without required settings: {', '.join(missing)}")
