"""Standalone-profile settings for PROlog.

In the integrated profile the ``prolog_surveys`` app is installed in the host
platform's Django project and that project's settings apply; the ``PROLOG_*``
values below document every setting the app reads (see ``prolog_surveys.conf``).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
REPO_ROOT = BASE_DIR.parent


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return [item for item in raw.split(os.pathsep) if item]


SECRET_KEY = os.environ.get("SECRET_KEY", "prolog-development-only-key")
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "prolog_surveys",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "prolog.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "prolog.wsgi.application"
ASGI_APPLICATION = "prolog.asgi.application"

# PostgreSQL only. There is no SQLite fallback in any profile (DEP-6).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "prolog"),
        "USER": os.environ.get("POSTGRES_USER", os.environ.get("USER", "prolog")),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Static files: the built runner (frontend/dist) is served by WhiteNoise.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
RUNNER_DIST = Path(os.environ.get("PROLOG_RUNNER_DIST", REPO_ROOT / "frontend" / "dist"))
STATICFILES_DIRS = [RUNNER_DIST] if RUNNER_DIST.exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_INDEX_FILE = True

CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.AcceptHeaderVersioning",
    "DEFAULT_VERSION": "1",
    "ALLOWED_VERSIONS": ["1"],
    "DEFAULT_THROTTLE_RATES": {
        "run.create": os.environ.get("PROLOG_THROTTLE_CREATE", "30/hour"),
        "run.answer": os.environ.get("PROLOG_THROTTLE_ANSWER", "600/hour"),
        "run.read": os.environ.get("PROLOG_THROTTLE_READ", "1200/hour"),
    },
}

# --- PROlog settings (see prolog_surveys/conf.py for defaults and docs) -----
PROLOG_PROFILE = os.environ.get("PROLOG_PROFILE", "standalone")
PROLOG_PARTICIPANT_MODEL = os.environ.get("PROLOG_PARTICIPANT_MODEL") or None
PROLOG_DEFINITION_DIRS = _env_list("PROLOG_DEFINITION_DIRS", [])
PROLOG_THEME_DIRS = _env_list("PROLOG_THEME_DIRS", [str(REPO_ROOT / "themes")])
PROLOG_SCHEMA_DIR = os.environ.get("PROLOG_SCHEMA_DIR", str(REPO_ROOT / "schema"))
PROLOG_IDENTITY_SERVICE = os.environ.get("PROLOG_IDENTITY_SERVICE") or None
PROLOG_CLIENT_KEY_SALT = os.environ.get("PROLOG_CLIENT_KEY_SALT", SECRET_KEY)
PROLOG_ABANDONED_RESPONSE_DAYS = int(os.environ.get("PROLOG_ABANDONED_RESPONSE_DAYS", "90"))
PROLOG_EMAIL_FROM = os.environ.get("PROLOG_EMAIL_FROM", "surveys@example.org")
PROLOG_PUBLIC_URL = os.environ.get("PROLOG_PUBLIC_URL", "http://localhost:5173")

MAILERS = {
    "default": {
        "BACKEND": os.environ.get(
            "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
        ),
    }
}

if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "true").lower() == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
