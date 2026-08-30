"""Identity capture for anonymous surveys in the integrated profile (CON-4).

The host platform provides a service that turns a consented email into a
participant record; PROlog only ever stores the resulting participant link.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from django.utils.module_loading import import_string

from . import conf


@dataclass(frozen=True)
class IdentityRequest:
    email: str
    idempotency_key: str
    survey_slug: str
    language: str


@dataclass(frozen=True)
class IdentityResult:
    participant_pk: Any


class IdentityService(Protocol):
    def create_or_link(self, request: IdentityRequest) -> IdentityResult: ...


class IdentityServiceError(Exception):
    """Raised by a service when the participant record cannot be created."""


def get_identity_service() -> IdentityService | None:
    path = conf.get("PROLOG_IDENTITY_SERVICE")
    if not path:
        return None
    target = import_string(path)
    return target() if isinstance(target, type) else target


def idempotency_key(response_id: Any) -> str:
    raw = f"{conf.get('PROLOG_CLIENT_KEY_SALT')}|identity|{response_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def resolve_participant(request) -> Any | None:
    """Participant pk for an authenticated request (account surveys)."""
    path = conf.get("PROLOG_PARTICIPANT_RESOLVER")
    if path:
        return import_string(path)(request)
    from django.conf import settings

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None
    if conf.participant_model() == settings.AUTH_USER_MODEL:
        return user.pk
    return None
