"""PROlog settings with defaults.

Every setting the reusable app reads is listed here so a host project
(integrated profile) can see the full surface. Read them through
``prolog_surveys.conf.get(name)``; never through ``django.conf.settings``
directly, so defaults apply uniformly.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

PROFILES = ("standalone", "integrated")

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
    # Dotted path to a callable implementing IdentityService (integrated only).
    "PROLOG_IDENTITY_SERVICE": None,
    # Dotted path to a callable (request) -> participant pk or None. Default: the
    # authenticated user's pk when PROLOG_PARTICIPANT_MODEL is AUTH_USER_MODEL.
    "PROLOG_PARTICIPANT_RESOLVER": None,
    # Salt for hashed client keys used by throttling (never stores raw IPs).
    "PROLOG_CLIENT_KEY_SALT": "prolog",
    # Trusted reverse proxies in front of the app. 0 = exposed directly (ignore
    # X-Forwarded-For / X-Forwarded-Proto); N = trust the last N hops.
    "PROLOG_NUM_PROXIES": 0,
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


def salted_hash(*parts: str) -> str:
    """SHA-256 of ``parts`` under PROLOG_CLIENT_KEY_SALT: the one recipe for
    every hashed identifier (client address, user agent, idempotency key)."""
    raw = "|".join((str(get("PROLOG_CLIENT_KEY_SALT")), *parts))
    return hashlib.sha256(raw.encode()).hexdigest()


def profile() -> str:
    return get("PROLOG_PROFILE")


def is_integrated() -> bool:
    return profile() == "integrated"


def participant_model() -> str | None:
    return get("PROLOG_PARTICIPANT_MODEL")


def schema_dir() -> Path:
    return Path(get("PROLOG_SCHEMA_DIR"))


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
