"""PROlog settings with defaults.

Every setting the reusable app reads is listed here so a host project
(integrated profile) can see the full surface. Read them through
``prolog_surveys.conf.get(name)``; never through ``django.conf.settings``
directly, so defaults apply uniformly.
"""

from __future__ import annotations

import hashlib
import warnings
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

PROFILES = ("standalone", "integrated")

# Throttle scopes the runner API uses and their default rates, keyed per hashed
# client address (``run.answer``: per response id). The standalone settings
# expose them as PROLOG_THROTTLE_* environment variables; an integrated host
# copies them into its REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] (a missing
# scope falls back to these, so nothing 500s).
THROTTLE_RATES: dict[str, str] = {
    "run.read": "1200/hour",
    "run.create": "30/hour",
    "run.capture": "30/hour",
    "run.answer": "600/hour",
}

# Salt values that are public or obviously unset. A salt is what keeps the
# hashed client addresses / user agents from being reversed by a dictionary
# attack, so a process never starts with one of these.
PLACEHOLDER_SALTS = frozenset({"", "prolog", "change-me"})

DEFAULTS: dict[str, Any] = {
    # "standalone": own database, no participant model, no identity service.
    # "integrated": installed in a host platform that provides both.
    "PROLOG_PROFILE": "standalone",
    # Dotted "app_label.ModelName" a response may link to (integrated only).
    "PROLOG_PARTICIPANT_MODEL": None,
    # Directories scanned for survey definition JSON files (loaded as drafts).
    "PROLOG_DEFINITION_DIRS": [],
    # Directories whose subdirectories contain theme.json + assets.
    "PROLOG_THEME_DIRS": [],
    # Directory holding survey-definition.schema.json and theme.schema.json.
    "PROLOG_SCHEMA_DIR": str(Path(__file__).resolve().parent.parent.parent / "schema"),
    # Dotted path to an IdentityService class, factory or instance (integrated only).
    "PROLOG_IDENTITY_SERVICE": None,
    # Dotted path to a callable (request) -> participant pk or None. Default: the
    # authenticated user's pk when PROLOG_PARTICIPANT_MODEL is AUTH_USER_MODEL.
    "PROLOG_PARTICIPANT_RESOLVER": None,
    # Salt for hashed client keys used by throttling (never stores raw IPs).
    # Unset = SECRET_KEY (see client_key_salt); rotate it to reset the counters.
    "PROLOG_CLIENT_KEY_SALT": None,
    # In-progress responses older than this are purged by `purge_abandoned_responses`.
    "PROLOG_ABANDONED_RESPONSE_DAYS": 90,
    "PROLOG_EMAIL_FROM": "surveys@example.org",
    # Public origin of the runner, used in invitation links.
    "PROLOG_PUBLIC_URL": "http://localhost:5173",
}


def get(name: str) -> Any:
    if name not in DEFAULTS:
        raise KeyError(f"Unknown PROlog setting {name}")
    return getattr(settings, name, DEFAULTS[name])


def client_key_salt() -> str:
    """PROLOG_CLIENT_KEY_SALT, or SECRET_KEY while it is unset or empty."""
    return str(get("PROLOG_CLIENT_KEY_SALT") or settings.SECRET_KEY)


def salted_hash(*parts: str) -> str:
    """SHA-256 of ``parts`` under the client key salt: the one recipe for
    every hashed identifier (client address, user agent, idempotency key)."""
    raw = "|".join((client_key_salt(), *parts))
    return hashlib.sha256(raw.encode()).hexdigest()


def profile() -> str:
    return get("PROLOG_PROFILE")


def is_integrated() -> bool:
    return profile() == "integrated"


def participant_model() -> str | None:
    return get("PROLOG_PARTICIPANT_MODEL")


def schema_dir() -> Path:
    return Path(get("PROLOG_SCHEMA_DIR"))


# The runner reads Django's CSRF cookie and echoes it in X-CSRFToken; a host
# that renames either, hides the cookie from scripts or moves the token into
# the session leaves session-authenticated participants unable to write.
_CSRF_DEFAULTS = {
    "CSRF_COOKIE_HTTPONLY": False,
    "CSRF_USE_SESSIONS": False,
    "CSRF_COOKIE_NAME": "csrftoken",
    "CSRF_HEADER_NAME": "HTTP_X_CSRFTOKEN",
}


def validate() -> None:
    """Fail fast on inconsistent settings (called from AppConfig.ready)."""
    prof = profile()
    if prof not in PROFILES:
        raise ImproperlyConfigured(f"PROLOG_PROFILE must be one of {PROFILES}, got {prof!r}")
    if prof == "standalone" and participant_model():
        raise ImproperlyConfigured(
            "PROLOG_PARTICIPANT_MODEL is only valid in the integrated profile"
        )
    if prof == "integrated" and not participant_model():
        raise ImproperlyConfigured("The integrated profile requires PROLOG_PARTICIPANT_MODEL")
    if not schema_dir().is_dir():
        raise ImproperlyConfigured(f"PROLOG_SCHEMA_DIR does not exist: {schema_dir()}")
    if client_key_salt().strip() in PLACEHOLDER_SALTS:
        raise ImproperlyConfigured(
            "PROLOG_CLIENT_KEY_SALT is a placeholder; set a secret value or leave it unset "
            "to derive it from SECRET_KEY"
        )
    if prof == "integrated":
        if get("PROLOG_IDENTITY_SERVICE"):
            from .identity import get_identity_service

            try:
                service = get_identity_service()
            except (ImportError, AttributeError, TypeError) as exc:
                raise ImproperlyConfigured(
                    f"PROLOG_IDENTITY_SERVICE could not be resolved: {exc}"
                ) from exc
            if not callable(getattr(service, "create_or_link", None)):
                raise ImproperlyConfigured(
                    "PROLOG_IDENTITY_SERVICE must resolve to an object with create_or_link()"
                )
        for name, expected in _CSRF_DEFAULTS.items():
            actual = getattr(settings, name, expected)
            if actual != expected:
                warnings.warn(
                    f"{name}={actual!r}: the survey runner reads the '{_CSRF_DEFAULTS['CSRF_COOKIE_NAME']}' "
                    "cookie and sends X-CSRFToken; session-authenticated participants "
                    "cannot answer unless the CSRF cookie and header keep Django's defaults",
                    stacklevel=2,
                )
