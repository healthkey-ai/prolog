"""Standalone-profile settings for PROlog.

In the integrated profile the ``prolog_surveys`` app is installed in the host
platform's Django project and that project's settings apply; the ``PROLOG_*``
values below document every setting the app reads (see ``prolog_surveys.conf``).
"""

import os
import re
import zoneinfo
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from prolog_surveys.conf import THROTTLE_RATE_RE, THROTTLE_RATES

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


def _throttle_rates() -> dict[str, str]:
    """PROLOG_THROTTLE_<SCOPE> overrides of prolog_surveys.conf.THROTTLE_RATES.

    Checked here because DRF parses a rate on the first request, not at boot:
    a malformed value would pass the health check and 500 every throttled
    endpoint. An empty variable means unset, like the other PROLOG_* values.
    """
    rates = {}
    for scope, default in THROTTLE_RATES.items():
        name = f"PROLOG_THROTTLE_{scope.removeprefix('run.').upper()}"
        value = os.environ.get(name, "").strip() or default
        if not THROTTLE_RATE_RE.match(value):
            raise ImproperlyConfigured(
                f"{name}={value!r} is not a rate DRF can parse (e.g. '30/hour')"
            )
        rates[scope] = value
    return rates


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
# Calendar dates (a survey's effective window, contact capture dates, the
# due dates of repeat schedules) are taken in this zone; set it to the
# deployment's local zone (an IANA name such as Europe/Paris). Default UTC.
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
try:
    zoneinfo.ZoneInfo(TIME_ZONE)
except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
    raise ImproperlyConfigured(f"TIME_ZONE is not an IANA time zone name: {TIME_ZONE!r}") from exc
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

# The runner API only ever receives small JSON bodies (an answer, an email);
# Django's 2.5 MB default would let an anonymous client push request-sized
# payloads at the unauthenticated endpoints. Definitions/themes are loaded
# from files, never uploaded.
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DATA_UPLOAD_MAX_MEMORY_SIZE", str(256 * 1024)))

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.AcceptHeaderVersioning",
    "DEFAULT_VERSION": "1",
    "ALLOWED_VERSIONS": ["1"],
    # PROLOG_THROTTLE_<SCOPE> overrides the defaults in prolog_surveys.conf.
    "DEFAULT_THROTTLE_RATES": _throttle_rates(),
    # Trusted reverse proxies for the client address behind the throttles (also
    # governs SECURE_PROXY_SSL_HEADER below); set from PROLOG_NUM_PROXIES.
    "NUM_PROXIES": int(os.environ.get("PROLOG_NUM_PROXIES", "0")),
}

# Throttle counters (and nothing else) live here. The default is per process:
# with N gunicorn workers each rate is effectively N times the configured
# value. For exact limits point CACHE_URL-style settings at a cache shared by
# all workers, e.g. CACHE_BACKEND=django.core.cache.backends.redis.RedisCache
# CACHE_LOCATION=redis://cache:6379/1 (or the database cache after
# `manage.py createcachetable`).
CACHES = {
    "default": {
        "BACKEND": os.environ.get("CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": os.environ.get("CACHE_LOCATION", "prolog"),
    }
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
PROLOG_NUM_PROXIES = REST_FRAMEWORK["NUM_PROXIES"]
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
