"""Standalone-profile settings for PROlog.

In the integrated profile the ``prolog_surveys`` app is installed in the host
platform's Django project and that project's settings apply; the ``PROLOG_*``
values below document every setting the app reads (see ``prolog_surveys.conf``).
"""

import os
import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
REPO_ROOT = BASE_DIR.parent


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return [item for item in raw.split(os.pathsep) if item]


def _env_csv(name: str, default: str) -> list[str]:
    """Comma-separated list; whitespace-tolerant and empty items dropped."""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


_DEV_SECRET_KEY = "prolog-development-only-key"
# Values that are public or obviously unset; a production process must never
# start with one (the key also salts the hashed client keys).
_PLACEHOLDER_SECRET_KEYS = {_DEV_SECRET_KEY, "change-me", ""}
SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_KEY)
# Off unless asked for: an unset variable must never leave a deployment serving
# tracebacks with the public development key (set DEBUG=true for local work).
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
if not DEBUG and SECRET_KEY.strip() in _PLACEHOLDER_SECRET_KEYS:
    raise ImproperlyConfigured("SECRET_KEY must be set to a real secret when DEBUG is false")
ALLOWED_HOSTS = _env_csv("ALLOWED_HOSTS", "localhost,127.0.0.1")

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
        # Reuse connections across requests (the runner autosaves per answer). Off
        # under DEBUG: the threaded dev server keeps one connection per request
        # thread and exhausts a local PostgreSQL. Override with CONN_MAX_AGE.
        "CONN_MAX_AGE": int(os.environ.get("CONN_MAX_AGE", "0" if DEBUG else "60")),
        "CONN_HEALTH_CHECKS": True,
    }
}

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Static files. Django's own static files (admin) live under STATIC_URL; the
# built runner (frontend/dist) is served by WhiteNoise at the site root, because
# its index.html references /assets/* (Vite's default base), not /static/.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
RUNNER_DIST = Path(os.environ.get("PROLOG_RUNNER_DIST", REPO_ROOT / "frontend" / "dist"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_ROOT = RUNNER_DIST if RUNNER_DIST.exists() else None
WHITENOISE_INDEX_FILE = True
# Vite names bundled assets <name>-<hash>.<ext>; they can be cached forever.
_VITE_ASSET_RE = re.compile(r"/assets/[^/]+-[A-Za-z0-9_-]{8,}\.[a-z0-9]+$")
WHITENOISE_IMMUTABLE_FILE_TEST = lambda path, url: bool(_VITE_ASSET_RE.search(url))  # noqa: E731

CORS_ALLOWED_ORIGINS = _env_csv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")

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
PROLOG_CLIENT_KEY_SALT = os.environ.get("PROLOG_CLIENT_KEY_SALT") or SECRET_KEY
PROLOG_ABANDONED_RESPONSE_DAYS = int(os.environ.get("PROLOG_ABANDONED_RESPONSE_DAYS", "90"))
PROLOG_EMAIL_FROM = os.environ.get("PROLOG_EMAIL_FROM", "surveys@example.org")
PROLOG_PUBLIC_URL = os.environ.get("PROLOG_PUBLIC_URL", "http://localhost:5173")
# Reverse proxies in front of the app (0 = exposed directly). When > 0 the
# proxy's X-Forwarded-For / X-Forwarded-Proto are trusted for throttling and
# for the HTTPS redirect; otherwise a client could spoof both.
PROLOG_NUM_PROXIES = int(os.environ.get("PROLOG_NUM_PROXIES", "0"))
if PROLOG_NUM_PROXIES > 0:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

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
    SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]  # readiness probes speak plain HTTP
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
