from pathlib import Path
from datetime import timedelta
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def load_local_env_file(path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env_file(BASE_DIR / ".env")
load_local_env_file(BASE_DIR / "backend" / ".env")


def parse_csv_setting(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def merge_csv_setting(env_name, defaults):
    values = []
    for item in [*defaults, *parse_csv_setting(os.environ.get(env_name, ""))]:
        if item not in values:
            values.append(item)
    return values

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
# Producción por defecto; habilita DEBUG sólo si DJANGO_DEBUG=true está seteado.
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"
_default_allowed_hosts = [
    "localhost",
    "127.0.0.1",
    "api.mativiglianco.cloud",
    "vales.mativiglianco.cloud",
    "31.97.86.142",
]
ALLOWED_HOSTS = merge_csv_setting("DJANGO_ALLOWED_HOSTS", _default_allowed_hosts)
_default_cors = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://api.mativiglianco.cloud",
    "https://vales.mativiglianco.cloud",
    "https://mativiglianco.github.io",
]
CORS_ALLOWED_ORIGINS = merge_csv_setting("CORS_ALLOWED_ORIGINS", _default_cors)
_default_csrf = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://api.mativiglianco.cloud",
    "https://vales.mativiglianco.cloud",
    "https://mativiglianco.github.io",
]
CSRF_TRUSTED_ORIGINS = merge_csv_setting("CSRF_TRUSTED_ORIGINS", _default_csrf)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'statsapp',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# DRF
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'statsapp.authentication.InactivityJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# CORS
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

JWT_REFRESH_COOKIE_NAME = 'refresh_token'
JWT_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True

# Keep imports bounded. Current account exports are allowed to be large, but not unbounded.
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE", 50 * 1024 * 1024))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DJANGO_FILE_UPLOAD_MAX_MEMORY_SIZE", 50 * 1024 * 1024))

# Custom auth/session settings
# Si quieres deshabilitar el cierre por inactividad, deja este valor en None.
INACTIVITY_TIMEOUT = None
